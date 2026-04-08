"""Clean and flatten US Congress legislator metadata.

Input
- 01_data/raw/us_congress/legislators-historical.json
- 01_data/raw/us_congress/legislators-current.json

Output
- 01_data/intermediate/politicians.csv
"""

from pathlib import Path
import argparse

import polars as pl


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def load_and_merge_legislators(root: Path) -> pl.DataFrame:
	src_historical = root / "01_data/raw/us_congress/legislators-historical.json"
	src_current = root / "01_data/raw/us_congress/legislators-current.json"

	df_historical = pl.read_json(src_historical, infer_schema_length=None)
	df_current = pl.read_json(src_current, infer_schema_length=None)

	# Align current columns and dtypes to historical, then stack them.
	hist_schema = df_historical.schema
	df_current_aligned = df_current.select(
		[
			(
				pl.col(col_name).cast(dtype, strict=False).alias(col_name)
				if col_name in df_current.columns
				else pl.lit(None, dtype=dtype).alias(col_name)
			)
			for col_name, dtype in hist_schema.items()
		]
	)

	return pl.concat([df_historical, df_current_aligned], how="vertical")


def build_people(df_raw: pl.DataFrame) -> pl.DataFrame:
	df_people = df_raw.unnest(["id", "name", "bio"])

	return (
		df_people.with_columns(
			pl.col("terms").list.len().fill_null(0).alias("n_terms"),
			pl.col("other_names").list.len().fill_null(0).alias("n_other_names"),
			pl.col("birthday").str.strptime(pl.Date, strict=False),
		)
		.rename(
			{
				"first": "first_name",
				"middle": "middle_name",
				"last": "last_name",
			}
		)
		.select(
			"bioguide",
			"first_name",
			"middle_name",
			"last_name",
			"suffix",
			"nickname",
			"official_full",
			"birthday",
			"gender",
			"govtrack",
			"icpsr",
			"house_history",
			"thomas",
			"lis",
			"cspan",
			"wikipedia",
			"wikidata",
			"google_entity_id",
			"n_terms",
			"n_other_names",
			"terms",
			"other_names",
		)
	)


def build_terms(people: pl.DataFrame) -> pl.DataFrame:
	return (
		people.select("bioguide", "terms")
		.explode("terms")
		.drop_nulls("terms")
		.unnest("terms")
		.with_columns(
			pl.col("start").str.strptime(pl.Date, strict=False),
			pl.col("end").str.strptime(pl.Date, strict=False),
		)
		.rename({"class": "senate_class", "type": "chamber"})
		.with_columns((pl.col("end") - pl.col("start")).dt.total_days().alias("term_days"))
	)


def build_people_flat(people: pl.DataFrame) -> pl.DataFrame:
	return people.drop(
		["terms", "other_names", "suffix", "nickname", "official_full", "thomas", "lis", "cspan"]
	)


def print_summary(people: pl.DataFrame, terms: pl.DataFrame) -> None:
	people_summary = people.select(
		pl.len().alias("n_people"),
		pl.col("bioguide").n_unique().alias("n_unique_bioguide"),
		pl.col("n_terms").sum().alias("total_terms_declared"),
		pl.col("n_other_names").sum().alias("total_other_names"),
	)

	terms_summary = terms.select(
		pl.len().alias("n_term_rows"),
		pl.col("chamber").n_unique().alias("n_chambers"),
		pl.col("state").n_unique().alias("n_states"),
		pl.col("party").n_unique().alias("n_parties"),
	)

	print("people summary")
	print(people_summary)
	print("terms summary")
	print(terms_summary)
	print("top null columns")
	print(
		people.null_count()
		.transpose(include_header=True, header_name="column", column_names=["n_null"])
		.sort("n_null", descending=True)
		.head(15)
	)


def main(save: bool = False) -> None:
	root = project_root()
	out_people = root / "01_data/intermediate/politicians.csv"

	df_raw = load_and_merge_legislators(root)
	people = build_people(df_raw)
	terms = build_terms(people)
	people_flat = build_people_flat(people)

	if save:
		out_people.parent.mkdir(parents=True, exist_ok=True)
		people_flat.write_csv(out_people)

	print("raw shape:", df_raw.shape)
	print("people shape:", people.shape)
	print("terms shape:", terms.shape)
	print("people_flat shape:", people_flat.shape)
	print_summary(people, terms)
	if save:
		print("saved:", out_people)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Clean legislators historical/current JSON files.")
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write cleaned CSV to 01_data/intermediate/politicians.csv.",
	)
	args = parser.parse_args()
	main(save=args.save)
