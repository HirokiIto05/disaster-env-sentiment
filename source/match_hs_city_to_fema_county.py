"""Match politician high-school cities to a Geocorr Place-to-County crosswalk.

Input
- 01_data/intermediate/politicians_hs_filled.csv
- A Geocorr CSV downloaded from MCDC with Place -> County correspondence

Output
- 01_data/intermediate/politicians_hs_county_matched.csv
"""

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


PLACE_PATTERNS = [
	r"place",
	r"placenm",
	r"placename",
	r"sourceplace",
	r"sourceplacenm",
	r"srcplace",
	r"srcplacenm",
]

COUNTY_PATTERNS = [
	r"county",
	r"countynm",
	r"countyname",
	r"targetcounty",
	r"targetcountynm",
	r"tgtcounty",
	r"tgtcountynm",
]

STATE_PATTERNS = [
	r"state",
	r"stateabbr",
	r"statecode",
	r"st",
	r"sourcestate",
	r"srcstate",
	r"targetstate",
	r"tgtstate",
]

AFACT_PATTERNS = [r"afact", r"allocationfactor", r"allocfactor"]
COUNTY_CODE_PATTERNS = [r"countyfips", r"countycode"]


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def normalize_column_name(name: str) -> str:
	return re.sub(r"[^a-z0-9]+", "", name.lower())


def pick_column(columns: list[str], patterns: list[str]) -> str | None:
	normalized = {normalize_column_name(column): column for column in columns}
	for pattern in patterns:
		for normalized_name, original_name in normalized.items():
			if re.fullmatch(pattern, normalized_name):
				return original_name
	for pattern in patterns:
		for normalized_name, original_name in normalized.items():
			if pattern in normalized_name:
				return original_name
	return None


def normalize_text(expr: pl.Expr) -> pl.Expr:
	return (
		expr.cast(pl.Utf8, strict=False)
		.str.to_uppercase()
		.str.replace_all("&", " AND ")
		.str.replace_all(r"[^A-Z0-9]+", " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def normalize_city(expr: pl.Expr) -> pl.Expr:
	return (
		normalize_text(expr)
		.str.replace_all(r",?\s+[A-Z]{2}$", "")
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
		if len(text) == 2:
			return text
		return STATE_MAP.get(text)

	return expr.map_elements(to_abbr, return_dtype=pl.Utf8)


def build_geocorr_lookup(df_crosswalk: pl.DataFrame) -> tuple[pl.DataFrame, bool]:
	place_column = pick_column(df_crosswalk.columns, PLACE_PATTERNS)
	county_column = pick_column(df_crosswalk.columns, COUNTY_PATTERNS)
	state_column = pick_column(df_crosswalk.columns, STATE_PATTERNS)
	afact_column = pick_column(df_crosswalk.columns, AFACT_PATTERNS)
	county_code_column = pick_column(df_crosswalk.columns, COUNTY_CODE_PATTERNS)

	if place_column is None or county_column is None:
		raise ValueError(
			"Could not identify place/county columns in the Geocorr file. "
			f"Available columns: {', '.join(df_crosswalk.columns)}"
		)

	select_exprs = [
		normalize_city(pl.col(place_column)).alias("geocorr_place_norm"),
		pl.col(place_column).cast(pl.Utf8, strict=False).str.strip_chars().alias("geocorr_place_name"),
		pl.col(county_column).cast(pl.Utf8, strict=False).str.strip_chars().alias("geocorr_county_name"),
	]

	if state_column is not None:
		select_exprs.append(normalize_state(pl.col(state_column)).alias("geocorr_state_abbr"))
	else:
		select_exprs.append(pl.lit(None, dtype=pl.Utf8).alias("geocorr_state_abbr"))

	if county_code_column is not None:
		select_exprs.append(
			pl.col(county_code_column).cast(pl.Utf8, strict=False).str.strip_chars().alias("geocorr_county_code"),
		)
	else:
		select_exprs.append(pl.lit(None, dtype=pl.Utf8).alias("geocorr_county_code"))

	if afact_column is not None:
		select_exprs.append(pl.col(afact_column).cast(pl.Float64, strict=False).alias("geocorr_afact"))
	else:
		select_exprs.append(pl.lit(None, dtype=pl.Float64).alias("geocorr_afact"))

	lookup = (
		df_crosswalk.select(select_exprs)
		.filter(
			pl.col("geocorr_place_norm").is_not_null()
			& (pl.col("geocorr_place_norm") != "")
			& pl.col("geocorr_county_name").is_not_null()
			& (pl.col("geocorr_county_name") != "")
		)
		.unique(subset=["geocorr_state_abbr", "geocorr_place_norm", "geocorr_county_name"])
	)

	return lookup, state_column is not None


def prepare_politicians(df_politicians: pl.DataFrame) -> pl.DataFrame:
	return df_politicians.with_columns(
		normalize_city(pl.col("hs_city")).alias("hs_city_norm"),
		normalize_state(pl.col("hs_state")).alias("hs_state_abbr"),
	)


def match_counties(df_politicians: pl.DataFrame, geocorr_lookup: pl.DataFrame, use_state: bool) -> pl.DataFrame:
	if use_state:
		joined = df_politicians.join(
			geocorr_lookup,
			left_on=["hs_state_abbr", "hs_city_norm"],
			right_on=["geocorr_state_abbr", "geocorr_place_norm"],
			how="left",
		)
	else:
		joined = df_politicians.join(
			geocorr_lookup,
			left_on=["hs_city_norm"],
			right_on=["geocorr_place_norm"],
			how="left",
		)

	return joined.with_columns(
		pl.lit("geocorr_place_county").alias("county_match_method"),
		pl.col("geocorr_county_name").is_not_null().alias("county_matched"),
	)


def main(save: bool = False, geocorr_path: str | None = None, primary_only: bool = False) -> None:
	root = project_root()
	path_politicians = root / "01_data/intermediate/politicians_hs_filled.csv"
	path_crosswalk = Path(geocorr_path) if geocorr_path is not None else root / "01_data/raw/geocorr/place_county.csv"
	out_path = root / "01_data/intermediate/politicians_hs_county_matched.csv"

	df_politicians = pl.read_csv(
		path_politicians,
		null_values=["NA", "", "N/A"],
		infer_schema_length=10000,
	)
	df_crosswalk = pl.read_csv(path_crosswalk, infer_schema_length=10000)

	geocorr_lookup, use_state = build_geocorr_lookup(df_crosswalk)
	df_prepared = prepare_politicians(df_politicians)
	df_result = match_counties(df_prepared, geocorr_lookup, use_state)

	if primary_only:
		df_result = (
			df_result.with_columns(pl.col("geocorr_afact").fill_null(-1.0).alias("_afact_sort"))
			.sort(["bioguide", "_afact_sort"], descending=[False, True])
			.group_by("bioguide", maintain_order=True)
			.first()
			.drop("_afact_sort")
		)

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
			"hs_city_norm",
			"hs_state_abbr",
			"geocorr_place_name",
			"geocorr_state_abbr",
			"geocorr_county_code",
			"geocorr_county_name",
			"geocorr_afact",
			"county_match_method",
			"county_matched",
		]
	)

	matched_count = df_result.select(pl.col("county_matched").sum().alias("matched_count")).item()
	print("rows:", df_result.height)
	print("matched:", matched_count)
	print("match rate:", round(matched_count / max(df_result.height, 1), 4))
	print("crosswalk path:", path_crosswalk)

	if save:
		out_path.parent.mkdir(parents=True, exist_ok=True)
		df_result.write_csv(out_path)
		print("saved:", out_path)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Match hs_city to a Geocorr Place-to-County crosswalk.")
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write matched CSV to 01_data/intermediate.",
	)
	parser.add_argument(
		"--geocorr-path",
		default=None,
		help="Path to a Geocorr CSV crosswalk file (Place -> County).",
	)
	parser.add_argument(
		"--primary-only",
		action="store_true",
		help="Keep only the county row with the highest allocation factor per politician.",
	)
	args = parser.parse_args()
	main(save=args.save, geocorr_path=args.geocorr_path, primary_only=args.primary_only)