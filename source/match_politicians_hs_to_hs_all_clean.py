"""Join politician high-school records to the cleaned school reference table.

Input
- 01_data/intermediate/politicians_hs.csv
- 01_data/intermediate/high_school/hs_all_clean.csv

Output
- 01_data/intermediate/politicians_hs_school_matched.csv
"""

from __future__ import annotations

from pathlib import Path
import argparse
import re

import polars as pl


STATE_MAP = {
	"ALABAMA": "AL",
	"ALASKA": "AK",
	"ARIZONA": "AZ",
	"ARKANSAS": "AR",
	"CALIFORNIA": "CA",
	"COLORADO": "CO",
	"CONNECTICUT": "CT",
	"DELAWARE": "DE",
	"DISTRICT OF COLUMBIA": "DC",
	"FLORIDA": "FL",
	"GEORGIA": "GA",
	"HAWAII": "HI",
	"IDAHO": "ID",
	"ILLINOIS": "IL",
	"INDIANA": "IN",
	"IOWA": "IA",
	"KANSAS": "KS",
	"KENTUCKY": "KY",
	"LOUISIANA": "LA",
	"MAINE": "ME",
	"MARYLAND": "MD",
	"MASSACHUSETTS": "MA",
	"MICHIGAN": "MI",
	"MINNESOTA": "MN",
	"MISSISSIPPI": "MS",
	"MISSOURI": "MO",
	"MONTANA": "MT",
	"NEBRASKA": "NE",
	"NEVADA": "NV",
	"NEW HAMPSHIRE": "NH",
	"NEW JERSEY": "NJ",
	"NEW MEXICO": "NM",
	"NEW YORK": "NY",
	"NORTH CAROLINA": "NC",
	"NORTH DAKOTA": "ND",
	"OHIO": "OH",
	"OKLAHOMA": "OK",
	"OREGON": "OR",
	"PENNSYLVANIA": "PA",
	"RHODE ISLAND": "RI",
	"SOUTH CAROLINA": "SC",
	"SOUTH DAKOTA": "SD",
	"TENNESSEE": "TN",
	"TEXAS": "TX",
	"UTAH": "UT",
	"VERMONT": "VT",
	"VIRGINIA": "VA",
	"WASHINGTON": "WA",
	"WEST VIRGINIA": "WV",
	"WISCONSIN": "WI",
	"WYOMING": "WY",
}


MANUAL_SCHOOL_NAME_REPLACEMENTS: list[tuple[str, str]] = [
	(r"\bHERBERT\s+HENRY\s+DOW\s+HIGH\s+SCHOOL\b", " HH DOW HIGH SCHOOL "),
	(r"\bWAHLERT\s+CATHOLIC\s+HIGH\s+SCHOOL\b", " HOLY FAMILY CATHOLIC SCHOOLS "), # school district name?
	(r"\bWAHLERT\s+HIGH\s+SCHOOL\b", " HOLY FAMILY CATHOLIC SCHOOLS "), # school district name?
	(r"\bCATHOLIC\s+MEMORIAL\s+HIGH\s+SCHOOL\b", " CATHOLIC MEMORIAL "), # address match
	(r"\bJERSEY\s+VILLAGE\s+HIGH\s+SCHOOL\b", " JERSEY VILLAGE H S "),
	(r"\bLA\s+LUMIERE\s+HIGH\s+SCHOOL\b", " LA LUMIERE SCHOOL "), # Mailing adress
	(r"\bFORT\s+HUNT\s+HIGH\s+SCHOOL\b", " SANDBURG MIDDLE "), # as of 2025
	(r"\bCOLUMBIA\s+CITY\s+JOINT\s+HIGH\s+SCHOOL\b", " COLUMBIA CITY HIGH SCHOOL "),
	(r"\bKIESTER\s+HIGH\s+SCHOOL\b", " UNITED SOUTH CENTRAL HIGH SCHOOL "), # Merge
	(r"\bMARY\s+D\.?\s+BRADFORD\s+HIGH\s+SCHOOL\b", " BRADFORD HIGH "),
	(r"\bDAYTON\s+UNION\s+HIGH\s+SCHOOL\b", " DAYTON HIGH SCHOOL "),
	(r"\bHUMBLE\s+HIGH\s+SCHOOL\b", " HUMBLE H S "),
	(r"\bARLINGTON\s+HEIGHTS\s+HIGH\s+SCHOOL\b", " ARLINGTON HEIGHTS H S "),
	(r"\bHARDY\s+PREPARATORY\s+SCHOOL\b", " HARDY BROWN COLLEGE PREP "),
	(r"\bWESTHAMPTON\s+BEACH\s+HIGH\s+SCHOOL\b", " WESTHAMPTON BEACH SENIOR HIGH SCHOOL "),
]


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def apply_manual_school_name_overrides(expr: pl.Expr) -> pl.Expr:
	result = expr
	for pattern, replacement in MANUAL_SCHOOL_NAME_REPLACEMENTS:
		result = result.str.replace_all(pattern, replacement)
	return result


def normalize_school_name(expr: pl.Expr) -> pl.Expr:
	base = expr.cast(pl.Utf8, strict=False).str.to_uppercase().str.replace_all("&", " AND ")
	base = pl.when(base.str.contains(r"\bACADEMY\b")).then(base.str.replace_all(r"^PHILLIPS\s+", "")).otherwise(base)
	base = apply_manual_school_name_overrides(base)
	return (
		base
		.str.replace_all(r"\bST\.?\b", " SAINT ")
		.str.replace_all(r"\bS\.?H\.?S\.?\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bSHS\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bH\.?S\.?\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bHS\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bHIGH\s+SCH\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bSENIOR\s+HIGH(?:\s+SCHOOL)?\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bJUNIOR\s+HIGH(?:\s+SCHOOL)?\b", " HIGH SCHOOL ")
		.str.replace_all(r"\bSR\.?\s+HIGH\b", " SENIOR HIGH ")
		.str.replace_all(r"\bJR\.?\s+HIGH\b", " JUNIOR HIGH ")
		.str.replace_all(r"\bHIGH$", " HIGH SCHOOL ")
		.str.replace_all(r"\bSCH\b", " SCHOOL ")
		.str.replace_all(r"[^A-Z0-9 ]", " ")
		.str.replace_all(r"\b(THE|OF|AND)\b", " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def normalize_city(expr: pl.Expr) -> pl.Expr:
	return (
		expr.cast(pl.Utf8, strict=False)
		.str.to_uppercase()
		.str.replace_all("&", " AND ")
		.str.replace_all(r"[^A-Z0-9]+", " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def normalize_state(expr: pl.Expr) -> pl.Expr:
	def to_abbr(value: object) -> object:
		if value is None:
			return None
		text = str(value).strip().upper()
		if not text or text == "NA":
			return None
		text = re.sub(r"\.", "", text)
		text = re.sub(r"\s+", " ", text)
		if len(text) == 2:
			return text
		return STATE_MAP.get(text)

	return expr.map_elements(to_abbr, return_dtype=pl.Utf8)


def clean_hs_reference(df_hs: pl.DataFrame) -> pl.DataFrame:
	return (
		df_hs.with_columns(
			normalize_school_name(pl.col("school_name")).alias("school_name_norm"),
			normalize_city(pl.col("city")).alias("school_city_norm"),
			normalize_state(pl.col("state")).alias("school_state_abbr"),
		)
		.filter(
			pl.col("school_name_norm").is_not_null()
			& (pl.col("school_name_norm") != "")
		)
		.unique(subset=["school_name_norm", "school_city_norm", "school_state_abbr"])
		.with_columns(
			pl.len().over("school_name_norm").alias("school_name_count"),
			pl.len().over(["school_name_norm", "school_state_abbr"]).alias("school_name_state_count"),
			pl.len().over(["school_name_norm", "school_state_abbr", "school_city_norm"]).alias(
				"school_name_state_city_count"
			),
		)
	)


def clean_politicians(df_politicians: pl.DataFrame) -> pl.DataFrame:
	return (
		df_politicians.with_row_index("row_id")
		.with_columns(
			normalize_school_name(pl.col("hs_name")).alias("hs_name_norm"),
			normalize_city(pl.col("hs_city")).alias("hs_city_norm"),
			normalize_state(pl.col("hs_state")).alias("hs_state_abbr"),
		)
		.filter(
			pl.col("hs_name_norm").is_not_null()
			& (pl.col("hs_name_norm") != "")
		)
	)


def build_match_candidates(df_politicians: pl.DataFrame, df_hs_ref: pl.DataFrame) -> pl.DataFrame:
	joined = df_politicians.join(
		df_hs_ref,
		left_on="hs_name_norm",
		right_on="school_name_norm",
		how="left",
	)

	joined = joined.with_columns(
		pl.col("school_name").is_not_null().sum().over("row_id").alias("candidate_rows"),
		(
			pl.col("hs_state_abbr").is_not_null()
			& pl.col("school_state_abbr").is_not_null()
			& (pl.col("hs_state_abbr") == pl.col("school_state_abbr"))
		).fill_null(False).alias("state_match"),
		(
			pl.col("hs_city_norm").is_not_null()
			& pl.col("school_city_norm").is_not_null()
			& (pl.col("hs_city_norm") == pl.col("school_city_norm"))
		).fill_null(False).alias("city_match"),
	)

	return joined.with_columns(
		(
			pl.col("state_match").cast(pl.Int8) * 2
			+ pl.col("city_match").cast(pl.Int8)
		).alias("match_score"),
		pl.when(pl.col("school_name").is_null())
		.then(pl.lit("no_match"))
		.when(pl.col("state_match") & pl.col("city_match"))
		.then(pl.lit("name_state_city"))
		.when(pl.col("state_match"))
		.then(pl.lit("name_state"))
		.when(pl.col("city_match"))
		.then(pl.lit("name_city"))
		.when(pl.col("candidate_rows") == 1)
		.then(pl.lit("name_only"))
		.when(pl.col("candidate_rows") > 1)
		.then(pl.lit("ambiguous_name_only"))
		.otherwise(pl.lit("name_only"))
		.alias("match_method"),
	)


def select_best_match(df_candidates: pl.DataFrame) -> pl.DataFrame:
	return (
		df_candidates.sort(
			[
				"row_id",
				"match_score",
				"school_name_state_city_count",
				"school_name_state_count",
				"school_name_count",
				"school_name",
				"school_city_norm",
				"school_state_abbr",
			],
			descending=[False, True, False, False, False, False, False, False],
		)
		.group_by("row_id", maintain_order=True)
		.first()
	)


def build_output(df_selected: pl.DataFrame) -> pl.DataFrame:
	return df_selected.select(
		[
			"bioguide",
			"first_name",
			"middle_name",
			"last_name",
			"birthday",
			"gender",
			"govtrack",
			"icpsr",
			"house_history",
			"wikipedia",
			"wikidata",
			"google_entity_id",
			"n_terms",
			"n_other_names",
			"birth_year",
			"hs_name",
			"hs_city",
			"hs_state",
			"hs_year",
			pl.col("school_id"),
			pl.col("school_name"),
			pl.col("city").alias("school_city"),
			pl.col("state").alias("school_state"),
			"school_year",
			"school_type",
			"match_method",
			"match_score",
			"candidate_rows",
			"state_match",
			"city_match",
		]
	)


def main(save: bool = False) -> None:
	root = project_root()
	path_politicians = root / "01_data/intermediate/politicians_hs.csv"
	path_hs_ref = root / "01_data/intermediate/high_school/hs_all_clean.csv"
	out_path = root / "01_data/intermediate/politicians_hs_school_matched.csv"

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
	if "school_type" not in df_hs_ref.columns and "source" in df_hs_ref.columns:
		df_hs_ref = df_hs_ref.rename({"source": "school_type"})

	df_politicians = clean_politicians(df_politicians)
	df_hs_ref = clean_hs_reference(df_hs_ref)
	df_candidates = build_match_candidates(df_politicians=df_politicians, df_hs_ref=df_hs_ref)
	df_best = select_best_match(df_candidates)
	df_out = build_output(df_best)

	matched_count = df_out.select(pl.col("school_id").is_not_null().sum().alias("matched_count")).item()
	row_count = df_out.height

	print("politician rows with hs_name:", row_count)
	print("matched rows:", matched_count)
	print("match rate:", round(matched_count / max(row_count, 1), 4))
	print(df_out.group_by("match_method").len().sort("len", descending=True))

	if save:
		out_path.parent.mkdir(parents=True, exist_ok=True)
		df_out.write_csv(out_path)
		print("saved:", out_path)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Match politician high school names to hs_all_clean.")
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write matched CSV to 01_data/intermediate/politicians_hs_school_matched.csv.",
	)
	args = parser.parse_args()
	main(save=args.save)
