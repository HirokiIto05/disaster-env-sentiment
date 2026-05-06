"""Bioguide text parser.

Purpose
- Extract high school information from bioguide biography text JSON.
- Reproduce the original qmd workflow as a Python module/script.

Input
- 01_data/raw/politician/bioguide_bio_raw.json
- 01_data/intermediate/politicians.csv

Output
- 01_data/intermediate/politicians_hs.csv
"""

from pathlib import Path
import argparse

import polars as pl


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def clean_public(df: pl.DataFrame) -> pl.DataFrame:
	return (
		df.select(
			[
				"NCESSCH",
				"NAME",
				"STREET",
				"CITY",
				"STATE",
				"ZIP",
				"STFIP",
				"CNTY",
				"NMCNTY",
				"LOCALE",
				"LAT",
				"LON",
				"CBSA",
				"NMCBSA",
				"CBSATYPE",
				"CSA",
				"NMCSA",
				"CD",
				"SLDL",
				"SLDU",
				"SCHOOLYEAR",
			]
		)
		.rename(
			{
				"NCESSCH": "school_id",
				"NAME": "school_name",
				"STREET": "street",
				"CITY": "city",
				"STATE": "state",
				"ZIP": "zip",
				"STFIP": "state_fips",
				"CNTY": "county_fips",
				"NMCNTY": "county_name",
				"LOCALE": "locale",
				"LAT": "lat",
				"LON": "lon",
				"CBSA": "cbsa",
				"NMCBSA": "nmcbsa",
				"CBSATYPE": "cbsa_type",
				"CSA": "csa",
				"NMCSA": "nmcsa",
				"CD": "cd",
				"SLDL": "sldl",
				"SLDU": "sldu",
				"SCHOOLYEAR": "school_year",
			}
		)
		.with_columns(
			pl.col("school_id").cast(pl.Utf8, strict=False),
			pl.col("zip").cast(pl.Utf8, strict=False).str.zfill(5),
			pl.col("county_fips").cast(pl.Utf8, strict=False).str.zfill(5),
			pl.col("state_fips").cast(pl.Utf8, strict=False).str.zfill(2),
			pl.col("cbsa_type").cast(pl.Utf8, strict=False),
			pl.lit("public").alias("school_type"),
		)
	)


def clean_private(df: pl.DataFrame) -> pl.DataFrame:
	return (
		df.select(
			[
				"PPIN",
				"PINST",
				"PADDRS",
				"PCITY",
				"PSTABB",
				"PZIP",
				"PCNTY22",
				"PCNTNM",
				"ULOCALE22",
				"LATITUDE22",
				"LONGITUDE22",
				"SLDLST22",
				"SLDUST22",
			]
		)
		.rename(
			{
				"PPIN": "school_id",
				"PINST": "school_name",
				"PADDRS": "street",
				"PCITY": "city",
				"PSTABB": "state",
				"PZIP": "zip",
				"PCNTY22": "county_fips",
				"PCNTNM": "county_name",
				"ULOCALE22": "locale",
				"LATITUDE22": "lat",
				"LONGITUDE22": "lon",
				"SLDLST22": "sldl",
				"SLDUST22": "sldu",
			}
		)
		.with_columns(
			pl.col("school_id").cast(pl.Utf8, strict=False),
			pl.col("zip").cast(pl.Utf8, strict=False).str.zfill(5),
			pl.col("county_fips").cast(pl.Utf8, strict=False).str.zfill(5),
			pl.lit(None).cast(pl.Utf8).alias("state_fips"),
			pl.lit(None).cast(pl.Utf8).alias("cbsa"),
			pl.lit(None).cast(pl.Utf8).alias("nmcbsa"),
			pl.lit(None).cast(pl.Utf8).alias("cbsa_type"),
			pl.lit(None).cast(pl.Utf8).alias("csa"),
			pl.lit(None).cast(pl.Utf8).alias("nmcsa"),
			pl.lit(None).cast(pl.Utf8).alias("cd"),
			pl.lit("2021-2022").alias("school_year"),
			pl.lit("private").alias("school_type"),
		)
	)


def main(save: bool = False) -> None:
	root = project_root()

	public_path = root / "01_data/raw/highschool/public/EDGE_GEOCODE_PUBLICSCH_2425.csv"
	private_path = root / "01_data/raw/highschool/private/pss2122_pu.csv"

	out_public = root / "01_data/intermediate/high_school/hs_public_clean.csv"
	out_private = root / "01_data/intermediate/high_school/hs_private_clean.csv"
	out_all = root / "01_data/intermediate/high_school/hs_all_clean.csv"

	df_pub_raw = pl.read_csv(
		public_path,
		schema_overrides={
			"ZIP": pl.Utf8,
			"STFIP": pl.Utf8,
			"CNTY": pl.Utf8,
			"CBSA": pl.Utf8,
			"CSA": pl.Utf8,
			"CD": pl.Utf8,
			"SLDL": pl.Utf8,
			"SLDU": pl.Utf8,
			"SCHOOLYEAR": pl.Utf8,
		},
	)
	df_private_raw = pl.read_csv(
		private_path,
		null_values=["N", "M"],
		infer_schema_length=10000,
	)

	df_pub = clean_public(df_pub_raw)
	df_private = clean_private(df_private_raw)

	ordered_cols = [
		"school_id",
		"school_name",
		"street",
		"city",
		"state",
		"zip",
		"state_fips",
		"county_fips",
		"county_name",
		"locale",
		"lat",
		"lon",
		"cbsa",
		"nmcbsa",
		"cbsa_type",
		"csa",
		"nmcsa",
		"cd",
		"sldl",
		"sldu",
		"school_year",
		"school_type",
	]

	df_pub = df_pub.select(ordered_cols)
	df_private = df_private.select(ordered_cols)
	df_all = pl.concat([df_pub, df_private], how="vertical")

	if save:
		out_public.parent.mkdir(parents=True, exist_ok=True)
		df_pub.write_csv(out_public)
		df_private.write_csv(out_private)
		df_all.write_csv(out_all)

	print("public shape:", df_pub.shape)
	print("private shape:", df_private.shape)
	print("all shape:", df_all.shape)
	print(df_all.group_by("school_type").len().sort("school_type"))
	if save:
		print("saved:", out_public)
		print("saved:", out_private)
		print("saved:", out_all)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Clean public/private high school files.")
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write cleaned CSV files to 01_data/intermediate/high_school.",
	)
	args = parser.parse_args()
	main(save=args.save)
