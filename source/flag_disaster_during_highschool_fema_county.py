from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl


COUNTY_SUFFIX_PATTERN = r"\b(COUNTY|PARISH|BOROUGH|CENSUS AREA|MUNICIPALITY|CITY AND BOROUGH|CITY AND COUNTY|DISTRICT|ISLAND)\b"


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def normalize_text(expr: pl.Expr) -> pl.Expr:
	return (
		expr.cast(pl.Utf8, strict=False)
		.str.to_uppercase()
		.str.replace_all(r"&", " AND ")
		.str.replace_all(r"[^A-Z0-9]+", " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def normalize_county_name(expr: pl.Expr) -> pl.Expr:
	return (
		normalize_text(expr)
		.str.replace_all(r"\([^)]*\)", " ")
		.str.replace_all(COUNTY_SUFFIX_PATTERN, " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def normalize_state(expr: pl.Expr) -> pl.Expr:
	return normalize_text(expr).str.replace_all(r"\bNA\b", "")


def prepare_school_reference(df_hs_ref: pl.DataFrame) -> pl.DataFrame:
	return (
		df_hs_ref.select(
			[
				"school_id",
				"school_name",
				"city",
				"state",
				"county_name",
			]
		)
		.with_columns(
			normalize_county_name(pl.col("county_name")).alias("school_county_name_norm"),
			normalize_state(pl.col("state")).alias("school_state_abbr"),
		)
	)


def prepare_politicians(df_politicians: pl.DataFrame, df_hs_ref: pl.DataFrame) -> pl.DataFrame:
	return (
		df_politicians.filter(pl.col("match_method") == "name_state_city")
		.join(
			df_hs_ref,
			on="school_id",
			how="left",
		)
		.with_columns(
			pl.col("hs_year").cast(pl.Int64, strict=False).alias("hs_grad_year_raw"),
			pl.col("birth_year").cast(pl.Int64, strict=False).alias("birth_year_int"),
			normalize_county_name(pl.col("county_name")).alias("school_county_name_norm"),
			normalize_state(pl.col("school_state")).alias("school_state_abbr"),
		)
		.with_columns(
			pl.coalesce(
				[
					pl.col("hs_grad_year_raw"),
					(pl.col("birth_year_int") + pl.lit(18)),
				]
			).alias("hs_grad_year")
		)
		.with_columns(
			(pl.col("hs_grad_year") - 3).alias("hs_start_year"),
			pl.col("hs_grad_year").alias("hs_end_year"),
		)
	)


def prepare_fema(df_fema: pl.DataFrame) -> pl.DataFrame:
	county_like_pattern = r"(?i)\b(county|parish|borough|census area|municipality|city and borough|city and county|district|island)\b"
	state_col = "stateCode" if "stateCode" in df_fema.columns else "state"
	county_col = "placeName" if "placeName" in df_fema.columns else "designatedArea"
	date_col = "designatedDate" if "designatedDate" in df_fema.columns else "declarationDate"

	missing_cols = [c for c in [state_col, county_col, date_col] if c not in df_fema.columns]
	if missing_cols:
		raise ValueError(f"Missing required disaster columns: {missing_cols}")

	return (
		df_fema.select(
			[
				"id",
				"disasterNumber",
				state_col,
				county_col,
				date_col,
			]
		)
		.with_columns(
			normalize_state(pl.col(state_col)).alias("state_abbr"),
			normalize_county_name(pl.col(county_col)).alias("fema_county_name_norm"),
			pl.col(date_col)
			.cast(pl.Utf8, strict=False)
			.str.slice(0, 4)
			.cast(pl.Int64, strict=False)
			.alias("disaster_year"),
		)
		.filter(
			pl.col("state_abbr").is_not_null()
			& (pl.col("state_abbr") != "")
			& pl.col("fema_county_name_norm").is_not_null()
			& (pl.col("fema_county_name_norm") != "")
			& pl.col(county_col).cast(pl.Utf8, strict=False).str.contains(county_like_pattern)
			& pl.col("disaster_year").is_not_null()
		)
		.unique(subset=["state_abbr", "fema_county_name_norm", "disaster_year", "disasterNumber"])
	)


def compute_overlap(df_politicians: pl.DataFrame, df_fema: pl.DataFrame) -> pl.DataFrame:
	df_valid = df_politicians.filter(
		pl.col("school_county_name_norm").is_not_null()
		& (pl.col("school_county_name_norm") != "")
		& pl.col("school_state_abbr").is_not_null()
		& (pl.col("school_state_abbr") != "")
		& pl.col("hs_start_year").is_not_null()
		& pl.col("hs_end_year").is_not_null()
	)

	df_expanded = (
		df_valid.with_columns(
			pl.int_ranges(
				pl.col("hs_start_year"),
				(pl.col("hs_end_year") + 1),
				eager=False,
			).alias("hs_years")
		)
		.explode("hs_years")
		.rename({"hs_years": "disaster_year"})
	)

	joined = df_expanded.join(
		df_fema,
		left_on=["school_state_abbr", "school_county_name_norm", "disaster_year"],
		right_on=["state_abbr", "fema_county_name_norm", "disaster_year"],
		how="left",
	)

	exposure = (
		joined.with_columns(pl.col("disasterNumber").is_not_null().cast(pl.Int64).alias("has_disaster"))
		.group_by("bioguide")
		.agg(
			pl.col("has_disaster").sum().alias("n_fema_disasters_hs_period"),
			pl.col("disasterNumber").drop_nulls().n_unique().alias("n_unique_fema_disasters_hs_period"),
		)
	)

	return (
		df_politicians.join(exposure, on="bioguide", how="left")
		.with_columns(
			pl.col("n_fema_disasters_hs_period").fill_null(0),
			pl.col("n_unique_fema_disasters_hs_period").fill_null(0),
			(pl.col("n_fema_disasters_hs_period") > 0).alias("had_fema_disaster_during_high_school"),
		)
	)


def main(save: bool = False, disaster_path: str | None = None) -> None:
	root = project_root()
	path_politicians = root / "01_data/intermediate/politicians_hs_school_matched.csv"
	path_hs_ref = root / "01_data/intermediate/high_school/hs_all_clean.csv"
	path_fema = Path(disaster_path) if disaster_path is not None else root / "01_data/raw/disaster/FemaWebDeclarationAreas.csv"
	out_path = root / "01_data/intermediate/politicians_hs_fema_county_flag.csv"

	df_politicians = pl.read_csv(
		path_politicians,
		null_values=["NA", "", "N/A"],
		infer_schema_length=10000,
	)
	df_hs_ref = pl.read_csv(
		path_hs_ref,
		null_values=["NA", "", "N", "M"],
		schema_overrides={
			"school_id": pl.Utf8,
			"state_fips": pl.Utf8,
			"county_fips": pl.Utf8,
			"zip": pl.Utf8,
			"sldl": pl.Utf8,
			"sldu": pl.Utf8,
			"school_year": pl.Utf8,
			"school_type": pl.Utf8,
		},
		infer_schema_length=10000,
	)
	df_fema = pl.read_csv(path_fema, infer_schema_length=10000)

	df_hs_ref_prepared = prepare_school_reference(df_hs_ref)
	df_politicians_prepared = prepare_politicians(df_politicians, df_hs_ref_prepared)
	df_fema_prepared = prepare_fema(df_fema)
	df_result = compute_overlap(df_politicians_prepared, df_fema_prepared)

	df_result = df_result.select(
		[
			"bioguide",
			"first_name",
			"middle_name",
			"last_name",
			"birth_year",
			"hs_name",
			"hs_city",
			"hs_state",
			"hs_year",
			"school_id",
			"school_name",
			"city",
			"state",
			"county_name",
			"hs_grad_year",
			"hs_start_year",
			"hs_end_year",
			"n_fema_disasters_hs_period",
			"n_unique_fema_disasters_hs_period",
			"had_fema_disaster_during_high_school",
		]
	)

	print("rows:", df_result.height)
	print("matched rows:", df_result.filter(pl.col("had_fema_disaster_during_high_school")).height)
	print(
		df_result.select(
			[
				pl.len().alias("n_total"),
				pl.col("had_fema_disaster_during_high_school").sum().alias("n_overlapped"),
				pl.col("county_name").is_null().sum().alias("n_missing_county"),
				pl.col("hs_grad_year").is_null().sum().alias("n_missing_hs_year"),
			]
		)
	)
	print(df_result.group_by("state").len().sort("len", descending=True).head(10))

	if save:
		out_path.parent.mkdir(parents=True, exist_ok=True)
		df_result.write_csv(out_path)
		print("saved:", out_path)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(
		description="Flag politicians whose high-school years overlap FEMA declaration areas in the school county."
	)
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write results to 01_data/intermediate/politicians_hs_fema_county_flag.csv.",
	)
	parser.add_argument(
		"--disaster-path",
		default=None,
		help="Path to disaster CSV (supports stateCode/placeName or state/designatedArea schema).",
	)
	args = parser.parse_args()
	main(save=args.save, disaster_path=args.disaster_path)