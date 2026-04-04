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

import json
import re
from collections import Counter
from pathlib import Path

import polars as pl
from pyprojroot import here


def build_state_mapping() -> dict[str, str]:
	"""Purpose
	- Provide state abbreviation to full-name mapping used by extraction.

	Input
	- None.

	Output
	- Dictionary mapping abbreviated state labels to canonical state names.
	"""
	return {
		"Ala.": "Alabama",
		"Alaska": "Alaska",
		"Ariz.": "Arizona",
		"Ark.": "Arkansas",
		"Calif.": "California",
		"Colo.": "Colorado",
		"Conn.": "Connecticut",
		"Del.": "Delaware",
		"Fla.": "Florida",
		"Ga.": "Georgia",
		"Hawaii": "Hawaii",
		"Idaho": "Idaho",
		"Ill.": "Illinois",
		"Ind.": "Indiana",
		"Iowa": "Iowa",
		"Kans.": "Kansas",
		"Ky.": "Kentucky",
		"La.": "Louisiana",
		"Maine": "Maine",
		"Md.": "Maryland",
		"Mass.": "Massachusetts",
		"Mich.": "Michigan",
		"Minn.": "Minnesota",
		"Miss.": "Mississippi",
		"Mo.": "Missouri",
		"Mont.": "Montana",
		"Nebr.": "Nebraska",
		"Nev.": "Nevada",
		"N.H.": "New Hampshire",
		"N.J.": "New Jersey",
		"N.Mex.": "New Mexico",
		"N.Y.": "New York",
		"N.C.": "North Carolina",
		"N.Dak.": "North Dakota",
		"Ohio": "Ohio",
		"Okla.": "Oklahoma",
		"Oreg.": "Oregon",
		"Pa.": "Pennsylvania",
		"R.I.": "Rhode Island",
		"S.C.": "South Carolina",
		"S.Dak.": "South Dakota",
		"Tenn.": "Tennessee",
		"Tex.": "Texas",
		"Utah": "Utah",
		"Vt.": "Vermont",
		"Va.": "Virginia",
		"Wash.": "Washington",
		"W.Va.": "West Virginia",
		"Wis.": "Wisconsin",
		"Wyo.": "Wyoming",
		"D.C.": "District of Columbia",
	}


def compile_patterns(state_abbr: dict[str, str]) -> dict[str, re.Pattern[str]]:
	"""Purpose
	- Compile all regex patterns used by the extractor.

	Input
	- state_abbr: state abbreviation mapping.

	Output
	- Dictionary of compiled regex patterns.
	"""
	state_pat_str = "|".join(re.escape(key) for key in state_abbr)
	city_pat = r"[A-Z][A-Za-z\.\'\-]*(?:\s+[A-Z][A-Za-z\.\'\-]*)*"
	hs_keywords = (
		r"(?:high school|senior high|academy|preparatory school|prep school|central school)"
	)

	hs_pat = re.compile(
		rf"(?:graduated from|graduated|attended)\s+"
		rf"((?:[A-Z][a-zA-Z\s\.\'\-]+?){hs_keywords})"
		rf"(?:,\s*"
		rf"(?:"
		rf"({city_pat}),\s*({state_pat_str})"
		rf"|({state_pat_str})"
		rf"|({city_pat})(?=,\s*\d{{4}}|[;\.,])"
		rf")"
		rf")?"
		rf"(?:,\s*(\d{{4}}))?",
		re.IGNORECASE,
	)  # [reason] Keep the original grouped pattern structure to preserve captures.

	public_multi_pat = re.compile(
		rf"(?:attended|educated in)\s+(?:the\s+)?public(?: and private)? schools in\s+"
		rf"({city_pat}),\s*({state_pat_str}),\s*and\s+"
		rf"({city_pat}),\s*({state_pat_str})(?=\s|[;,\.]|$)",
		re.IGNORECASE,
	)

	private_pat = re.compile(
		rf"(?:attended|educated in)\s+(?:the\s+)?private schools in\s+"
		rf"({city_pat}),\s*({state_pat_str})(?=\s|[;,\.]|$)",
		re.IGNORECASE,
	)

	public_pat_with_state = re.compile(
		rf"(?:attended|educated in)\s+(?:the\s+)?"
		rf"(?:(?:public schools)\s+(?:of|in)\s+({city_pat}),\s*({state_pat_str})"
		rf"|(?:grammar school)\s+in\s+({city_pat}),\s*({state_pat_str}))"
		rf"(?=\s|[;,\.]|$)",
		re.IGNORECASE,
	)

	public_pat_without_state = re.compile(
		rf"(?:attended|educated in)\s+(?:the\s+)?"
		rf"(?:(?:public schools)\s+(?:of|in)\s+({city_pat})"
		rf"|(?:grammar school)\s+in\s+({city_pat}))"
		rf"[;,\.]",
		re.IGNORECASE,
	)

	print("パターン定義完了")  # [reason] Match the original qmd status message exactly.

	return {
		"HS_PAT": hs_pat,
		"PUBLIC_MULTI_PAT": public_multi_pat,
		"PRIVATE_PAT": private_pat,
		"PUBLIC_PAT_WITH_STATE": public_pat_with_state,
		"PUBLIC_PAT_WITHOUT_STATE": public_pat_without_state,
	}


def extract_hs(
	bid: str,
	text: str,
	state_abbr: dict[str, str],
	patterns: dict[str, re.Pattern[str]],
) -> dict[str, str]:
	"""Purpose
	- Extract high school-related fields from one biography text.

	Input
	- bid: bioguide id.
	- text: biography text.
	- state_abbr: state abbreviation mapping.
	- patterns: compiled regex patterns.

	Output
	- Record with school name, city, state, year, and matched pattern type.
	"""
	base = {
		"bioguide": bid,
		"hs_name": "",
		"hs_city": "",
		"hs_state": "",
		"hs_year": "",
		"pattern": "none",
	}
	if not text:
		return base

	m0 = patterns["PUBLIC_MULTI_PAT"].search(text)
	if m0:
		city = m0.group(1).strip()
		state_key = m0.group(2).strip()
		return {
			**base,
			"hs_city": city,
			"hs_state": state_abbr.get(state_key, ""),
			"pattern": "public_schools_multi",
		}

	m1 = patterns["PRIVATE_PAT"].search(text)
	if m1:
		city = m1.group(1).strip()
		state_key = m1.group(2).strip()
		return {
			**base,
			"hs_city": city,
			"hs_state": state_abbr.get(state_key, ""),
			"pattern": "private_schools",
		}

	m2 = patterns["PUBLIC_PAT_WITH_STATE"].search(text)
	if m2:
		city = (m2.group(1) or m2.group(3) or "").strip()
		state_key = (m2.group(2) or m2.group(4) or "").strip()
		return {
			**base,
			"hs_city": city,
			"hs_state": state_abbr.get(state_key, ""),
			"pattern": "public_schools",
		}

	m2 = patterns["PUBLIC_PAT_WITHOUT_STATE"].search(text)
	if m2:
		city = (m2.group(1) or m2.group(2) or "").strip()
		return {
			**base,
			"hs_city": city,
			"hs_state": "",
			"pattern": "public_schools",
		}

	m = patterns["HS_PAT"].search(text)
	if m:
		school = m.group(1).strip().rstrip(",")
		city = (m.group(2) or m.group(5) or "").strip()
		state_key = (m.group(3) or m.group(4) or "").strip()
		year = (m.group(6) or "").strip()
		return {
			**base,
			"hs_name": school,
			"hs_city": city,
			"hs_state": state_abbr.get(state_key, ""),
			"hs_year": year,
			"pattern": "graduated_attended",
		}  # [reason] Preserve original matching order and field fallback behavior.

	return base


def load_raw_bioguide_json(raw_json_path: Path) -> dict[str, str]:
	"""Purpose
	- Load raw bioguide biography JSON.

	Input
	- raw_json_path: path to bioguide_bio_raw.json.

	Output
	- Mapping from bioguide id to biography text.
	"""
	with open(raw_json_path, encoding="utf-8") as file:
		return json.load(file)


def create_bio_dataframe(
	raw: dict[str, str],
	state_abbr: dict[str, str],
	patterns: dict[str, re.Pattern[str]],
) -> pl.DataFrame:
	"""Purpose
	- Apply extraction to all biographies and return a Polars DataFrame.

	Input
	- raw: mapping of bioguide id to text.
	- state_abbr: state abbreviation mapping.
	- patterns: compiled regex patterns.

	Output
	- DataFrame with extracted high school fields and pattern labels.
	"""
	records = [
		extract_hs(bid=bid, text=text, state_abbr=state_abbr, patterns=patterns)
		for bid, text in raw.items()
	]
	return pl.DataFrame(records)


def print_coverage(records: list[dict[str, str]]) -> None:
	"""Purpose
	- Print extraction coverage metrics and pattern counts.

	Input
	- records: list of extraction result records.

	Output
	- None. Prints summary statistics.
	"""
	total = len(records)
	has_name = sum(1 for record in records if record["hs_name"])
	has_city = sum(1 for record in records if record["hs_city"])
	has_state = sum(1 for record in records if record["hs_state"])
	has_both = sum(1 for record in records if record["hs_name"] and record["hs_state"])
	has_name_or_city = sum(1 for record in records if record["hs_name"] or record["hs_city"])
	pattern_ct = Counter(record["pattern"] for record in records)

	print("=== Coverage ===")  # [reason] Match the original qmd coverage label.
	print(f"Total               : {total:>4}")
	print(f"Has high school name: {has_name:>4} ({has_name / total * 100:.1f}%)")
	print(f"Has city            : {has_city:>4} ({has_city / total * 100:.1f}%)")
	print(f"Has state           : {has_state:>4} ({has_state / total * 100:.1f}%)")
	print(f"Has name + state    : {has_both:>4} ({has_both / total * 100:.1f}%)")
	print(f"Has name or city    : {has_name_or_city:>4} ({has_name_or_city / total * 100:.1f}%)")
	print("\n=== By Pattern ===")
	for key, value in pattern_ct.most_common():
		print(f"  {key:<25}: {value:>4} cases")


def build_filtered_hs_dataframe(df_bio: pl.DataFrame) -> pl.DataFrame:
	"""Purpose
	- Keep only rows with at least a school name or city, then select output columns.

	Input
	- df_bio: extraction result dataframe.

	Output
	- Filtered dataframe with the five output columns.
	"""
	return (
		df_bio.filter((pl.col("hs_name") != "") | (pl.col("hs_city") != ""))
		.select("bioguide", "hs_name", "hs_city", "hs_state", "hs_year")
	)


def build_merged_dataframe(project_root: Path, df_hs: pl.DataFrame) -> pl.DataFrame:
	"""Purpose
	- Reproduce the qmd merge step with politicians metadata.

	Input
	- project_root: project root path.
	- df_hs: filtered high school dataframe.

	Output
	- Merged dataframe used for final CSV export.
	"""
	df_main = (
		pl.read_csv(project_root / "01_data" / "intermediate" / "politicians.csv")
		.with_columns(
			pl.col("birthday").str.slice(0, 4).cast(pl.Int32, strict=False).alias("birth_year")
		)
		.filter(pl.col("birth_year").is_not_null() & (pl.col("birth_year") >= 1946))
	)
	return (
		df_main.join(df_hs, on="bioguide", how="left")
		.filter(pl.col("hs_name").is_not_null())
	)  # [reason] Keep original join type and null filter semantics.


def run_pipeline(project_root: Path) -> None:
	"""Purpose
	- Execute the full extraction and merge pipeline.

	Input
	- project_root: project root path.

	Output
	- None. Writes the final CSV and prints progress/coverage.
	"""
	out_dir = project_root / "01_data" / "raw" / "politician"
	raw_json_path = out_dir / "bioguide_bio_raw.json"
	out_csv_path = out_dir / "bioguide_hs.csv"  # [reason] Preserve displayed output path from the qmd setup cell.
	final_csv_path = project_root / "01_data" / "intermediate" / "politicians_hs.csv"

	state_abbr = build_state_mapping()
	patterns = compile_patterns(state_abbr)

	raw = load_raw_bioguide_json(raw_json_path)
	records = [
		extract_hs(bid=bid, text=text, state_abbr=state_abbr, patterns=patterns)
		for bid, text in raw.items()
	]
	df_bio = pl.DataFrame(records)

	print_coverage(records)

	df_hs = build_filtered_hs_dataframe(df_bio)
	df_merge = build_merged_dataframe(project_root=project_root, df_hs=df_hs)
	df_merge.write_csv(final_csv_path)  # [reason] Keep the original final write target unchanged.


def main() -> None:
	"""Purpose
	- Script entry point.

	Input
	- None.

	Output
	- None.
	"""
	project_root = here()
	run_pipeline(project_root=project_root)


if __name__ == "__main__":
	main()
