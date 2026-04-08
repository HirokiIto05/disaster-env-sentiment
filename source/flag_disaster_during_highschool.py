from pathlib import Path
import argparse

import polars as pl


def project_root() -> Path:
	return Path(__file__).resolve().parents[1]


def normalize_text(expr: pl.Expr) -> pl.Expr:
	return (
		expr.cast(pl.Utf8, strict=False)
		.str.to_uppercase()
		.str.replace_all(r"[^A-Z0-9]+", " ")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def extract_incident_city(expr: pl.Expr) -> pl.Expr:
	# Heuristic city extraction from free-text incident names.
	return (
		normalize_text(expr)
		.str.replace(r"^[A-Z]{2}\s+", "")
		.str.replace(r"^R[0-9]+\s+", "")
		.str.replace(
			r"\b(SEVERE|STORMS?|TORNADO(ES)?|FLOOD(ING)?|HURRICANE|FIRES?|WILDFIRE|MUD|LANDSLIDE|SNOW|ICE|EXPLOSION(S)?|EARTHQUAKE|DROUGHT|WEATHER|THUNDERSTORMS?|RAIN|WINTER|NOR ?EASTER|TS|POSSIBLE|POWER|OUTAGE|EMERGENCY|DISASTER)\b.*$",
			"",
		)
		.str.replace(r"\b[0-9]{1,4}\b.*$", "")
		.str.replace_all(r"\s+", " ")
		.str.strip_chars()
	)


def build_state_name_map(df_disaster: pl.DataFrame) -> pl.DataFrame:
	return (
		df_disaster.select(
			pl.col("stateAbbreviation").cast(pl.Utf8).str.strip_chars().alias("state_abbr"),
			normalize_text(pl.col("state")).alias("state_norm"),
		)
		.filter(
			pl.col("state_abbr").is_not_null()
			& (pl.col("state_abbr") != "")
			& pl.col("state_norm").is_not_null()
			& (pl.col("state_norm") != "")
		)
		.unique(subset=["state_abbr", "state_norm"])
	)


def infer_state_from_school(df_hs_ref: pl.DataFrame) -> pl.DataFrame:
	unique_school_city = (
		df_hs_ref.select(
			normalize_text(pl.col("school_name")).alias("hs_name_norm"),
			normalize_text(pl.col("city")).alias("hs_city_norm"),
			pl.col("state").cast(pl.Utf8, strict=False).str.strip_chars().alias("state_abbr"),
		)
		.filter(
			pl.col("hs_name_norm").is_not_null()
			& (pl.col("hs_name_norm") != "")
			& pl.col("hs_city_norm").is_not_null()
			& (pl.col("hs_city_norm") != "")
			& pl.col("state_abbr").is_not_null()
			& (pl.col("state_abbr") != "")
		)
	)

	return (
		unique_school_city.group_by(["hs_name_norm", "hs_city_norm"])
		.agg(
			pl.col("state_abbr").n_unique().alias("n_states"),
			pl.col("state_abbr").first().alias("state_abbr_from_hs_ref"),
		)
		.filter(pl.col("n_states") == 1)
		.select(["hs_name_norm", "hs_city_norm", "state_abbr_from_hs_ref"])
	)


def prepare_politicians(
	df_politicians: pl.DataFrame,
	state_name_map: pl.DataFrame,
	hs_state_lookup: pl.DataFrame,
) -> pl.DataFrame:
	df = df_politicians.with_columns(
		normalize_text(pl.col("hs_name")).alias("hs_name_norm"),
		normalize_text(pl.col("hs_city")).alias("hs_city_norm"),
		normalize_text(pl.col("hs_state")).alias("hs_state_norm"),
		pl.col("hs_year").cast(pl.Int64, strict=False).alias("hs_grad_year_raw"),
		pl.col("birth_year").cast(pl.Int64, strict=False).alias("birth_year_int"),
	)

	df = df.join(
		state_name_map,
		left_on="hs_state_norm",
		right_on="state_norm",
		how="left",
	)
	# If hs_state is already a two-letter abbreviation, use it directly.
	df = df.with_columns(
		pl.when(pl.col("hs_state_norm").str.len_chars() == 2)
		.then(pl.col("hs_state_norm"))
		.otherwise(pl.col("state_abbr"))
		.alias("state_abbr_from_hs_text")
	)

	df = df.join(hs_state_lookup, on=["hs_name_norm", "hs_city_norm"], how="left")

	df = df.with_columns(
		pl.coalesce(
			[
				pl.col("state_abbr_from_hs_text"),
				pl.col("state_abbr_from_hs_ref"),
			]
		)
		.str.to_uppercase()
		.alias("hs_state_abbr"),
		pl.coalesce(
			[
				pl.col("hs_grad_year_raw"),
				(pl.col("birth_year_int") + pl.lit(18)),
			]
		).alias("hs_grad_year"),
	)

	return df.with_columns(
		(pl.col("hs_grad_year") - 3).alias("hs_start_year"),
		pl.col("hs_grad_year").alias("hs_end_year"),
		pl.col("hs_grad_year_raw").is_null().alias("hs_grad_year_imputed"),
	)


def compute_exposure(df_politicians: pl.DataFrame, df_disaster: pl.DataFrame) -> pl.DataFrame:
	disaster_city_years = (
		df_disaster.with_columns(
			pl.col("stateAbbreviation").cast(pl.Utf8).str.strip_chars().alias("state_abbr"),
			extract_incident_city(pl.col("incidentName")).alias("incident_city_norm"),
			pl.col("incidentBeginDate")
			.cast(pl.Utf8, strict=False)
			.str.slice(0, 4)
			.cast(pl.Int64, strict=False)
			.alias("incident_year"),
		)
		.filter(
			pl.col("state_abbr").is_not_null()
			& (pl.col("state_abbr") != "")
			& pl.col("incident_city_norm").is_not_null()
			& (pl.col("incident_city_norm") != "")
			& (pl.col("incident_city_norm").str.len_chars() >= 3)
			& pl.col("incident_year").is_not_null()
		)
		.group_by(["state_abbr", "incident_city_norm", "incident_year"])
		.agg(pl.len().alias("n_disasters_in_year"))
	)

	df_valid = df_politicians.filter(
		pl.col("hs_state_abbr").is_not_null()
		& (pl.col("hs_state_abbr") != "")
		& pl.col("hs_city_norm").is_not_null()
		& (pl.col("hs_city_norm") != "")
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
		.rename({"hs_years": "incident_year"})
	)

	exposure = (
		df_expanded.join(
			disaster_city_years,
			left_on=["hs_state_abbr", "hs_city_norm", "incident_year"],
			right_on=["state_abbr", "incident_city_norm", "incident_year"],
			how="left",
		)
		.with_columns(pl.col("n_disasters_in_year").fill_null(0))
		.group_by("bioguide")
		.agg(pl.col("n_disasters_in_year").sum().alias("n_disasters_hs_period"))
	)

	return (
		df_politicians.join(exposure, on="bioguide", how="left")
		.with_columns(
			pl.col("n_disasters_hs_period").fill_null(0),
			(pl.col("n_disasters_hs_period") > 0).alias("had_disaster_during_high_school"),
		)
	)


def main(save: bool = False) -> None:
	root = project_root()

	path_disaster = root / "01_data/raw/disaster/DeclarationDenials.csv"
	path_politicians = root / "01_data/intermediate/politicians_hs_filled.csv"
	path_hs_ref = root / "01_data/intermediate/high_school/hs_all_clean.csv"
	out_path = root / "01_data/intermediate/politicians_hs_disaster_flag.csv"

	df_disaster = pl.read_csv(path_disaster, infer_schema_length=10000)
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
			"cbsa": pl.Utf8,
			"csa": pl.Utf8,
			"cd": pl.Utf8,
			"sldl": pl.Utf8,
			"sldu": pl.Utf8,
		},
		infer_schema_length=10000,
	)

	state_name_map = build_state_name_map(df_disaster)
	hs_state_lookup = infer_state_from_school(df_hs_ref)

	df_prepared = prepare_politicians(df_politicians, state_name_map, hs_state_lookup)
	df_result = compute_exposure(df_prepared, df_disaster)

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
			"hs_state_abbr",
			"hs_year",
			"hs_grad_year",
			"hs_grad_year_imputed",
			"hs_start_year",
			"hs_end_year",
			"n_disasters_hs_period",
			"had_disaster_during_high_school",
		]
	)

	print("rows:", df_result.height)
	print("columns:", df_result.width)
	print(
		df_result.select(
			[
				pl.len().alias("n_total"),
				pl.col("had_disaster_during_high_school").sum().alias("n_had_disaster"),
				pl.col("hs_state_abbr").is_null().sum().alias("n_missing_state"),
				pl.col("hs_grad_year_imputed").sum().alias("n_imputed_grad_year"),
			]
		)
	)

	if save:
		out_path.parent.mkdir(parents=True, exist_ok=True)
		df_result.write_csv(out_path)
		print("saved:", out_path)
	else:
		print("no files were written (preview mode).")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(
		description="Flag whether each politician experienced a disaster during high school years."
	)
	parser.add_argument(
		"--save",
		action="store_true",
		help="Write results to 01_data/intermediate/politicians_hs_disaster_flag.csv.",
	)
	args = parser.parse_args()
	main(save=args.save)
