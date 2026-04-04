library(here)
library(dplyr)
library(readr)
library(stringr)

df_hs <- read_csv(here("01_data/intermediate/high_school/hs_all_clean.csv"), show_col_types = FALSE)
df_politician <- read_csv(here("01_data/intermediate/politicians_hs.csv"), show_col_types = FALSE)

normalize_school_name <- function(x) {
	x |>
		str_to_upper() |>
		str_replace_all("&", " AND ") |>
			# 例: PHILLIPS EXETER ACADEMY -> EXETER ACADEMY
			str_replace("^PHILLIPS\\s+(?=.+\\bACADEMY\\b)", "") |>
		# よくある略記ゆれを展開
		str_replace_all("\\bS\\.?H\\.?S\\.?\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bSHS\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bH\\.?S\\.?\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bHS\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bHIGH\\s+SCH\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bSENIOR\\s+HIGH\\s+SCHOOL\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bSENIOR\\s+HIGH\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bJR\\.?\\s+HIGH\\s+SCHOOL\\b", " HIGH SCHOOL ") |>
		str_replace_all("\\bJUNIOR\\s+HIGH\\s+SCHOOL\\b", " HIGH SCHOOL ") |>
		# 語尾の HIGH を HIGH SCHOOL とみなす（例: GREAT MILLS HIGH）
		str_replace_all("\\bHIGH$", " HIGH SCHOOL ") |>
		str_replace_all("\\bSCH\\b", " SCHOOL ") |>
		str_replace_all("\\bSR\\s+HIGH\\b", " SENIOR HIGH ") |>
		str_replace_all("\\bJR\\s+HIGH\\b", " JUNIOR HIGH ") |>
		str_replace_all("[^A-Z0-9 ]", " ") |>
		# 結合に効きにくい機能語は除去
		str_replace_all("\\b(THE|OF|AND)\\b", " ") |>
		str_squish()
}

normalize_state <- function(x) {
	state_map <- c(
		"ALABAMA" = "AL", "ALASKA" = "AK", "ARIZONA" = "AZ", "ARKANSAS" = "AR",
		"CALIFORNIA" = "CA", "COLORADO" = "CO", "CONNECTICUT" = "CT", "DELAWARE" = "DE",
		"DISTRICT OF COLUMBIA" = "DC", "FLORIDA" = "FL", "GEORGIA" = "GA", "HAWAII" = "HI",
		"IDAHO" = "ID", "ILLINOIS" = "IL", "INDIANA" = "IN", "IOWA" = "IA", "KANSAS" = "KS",
		"KENTUCKY" = "KY", "LOUISIANA" = "LA", "MAINE" = "ME", "MARYLAND" = "MD",
		"MASSACHUSETTS" = "MA", "MICHIGAN" = "MI", "MINNESOTA" = "MN", "MISSISSIPPI" = "MS",
		"MISSOURI" = "MO", "MONTANA" = "MT", "NEBRASKA" = "NE", "NEVADA" = "NV",
		"NEW HAMPSHIRE" = "NH", "NEW JERSEY" = "NJ", "NEW MEXICO" = "NM", "NEW YORK" = "NY",
		"NORTH CAROLINA" = "NC", "NORTH DAKOTA" = "ND", "OHIO" = "OH", "OKLAHOMA" = "OK",
		"OREGON" = "OR", "PENNSYLVANIA" = "PA", "RHODE ISLAND" = "RI", "SOUTH CAROLINA" = "SC",
		"SOUTH DAKOTA" = "SD", "TENNESSEE" = "TN", "TEXAS" = "TX", "UTAH" = "UT", "VERMONT" = "VT",
		"VIRGINIA" = "VA", "WASHINGTON" = "WA", "WEST VIRGINIA" = "WV", "WISCONSIN" = "WI", "WYOMING" = "WY"
	)

	y <- x |>
		str_to_upper() |>
		str_replace_all("\\.", "") |>
		str_squish()
}

hs_ref <- df_hs |>
	transmute(
		key_name = normalize_school_name(school_name),
		school_city = city,
		school_state = normalize_state(state)
	) |>
	filter(!is.na(key_name), key_name != "", !is.na(school_city), str_squish(school_city) != "")

# 同名校が複数都市にある場合に備えて重複除去
hs_ref_unique <- hs_ref |>
	distinct(key_name, school_city, school_state)

df_politician_filled <- df_politician |>
	mutate(
		row_id = row_number(),
		key_name = normalize_school_name(hs_name),
		key_state = normalize_state(hs_state),
		hs_city_missing = is.na(hs_city) | str_squish(hs_city) == ""
	) |>
	left_join(hs_ref_unique, by = "key_name", relationship = "many-to-many") |>
	group_by(row_id) |>
	mutate(
		state_match = !is.na(key_state) & !is.na(school_state) & key_state == school_state,
		has_state_match = any(state_match, na.rm = TRUE)
	) |>
	filter(if_else(has_state_match, state_match, TRUE)) |>
	mutate(
		hs_city = if_else(hs_city_missing & !is.na(school_city), school_city, hs_city)
	) |>
	slice(1) |>
	ungroup() |>
	select(-row_id, -key_name, -key_state, -hs_city_missing, -school_city, -school_state, -state_match, -has_state_match)

before_missing <- sum(is.na(df_politician$hs_city) | str_squish(df_politician$hs_city) == "")
after_missing <- sum(is.na(df_politician_filled$hs_city) | str_squish(df_politician_filled$hs_city) == "")
df_politician_filled |> 
  dplyr::filter(is.na(hs_city)) |> 
	distinct(hs_name) |> pull()
cat("Missing hs_city (before):", before_missing, "\n")
cat("Missing hs_city (after):", after_missing, "\n")
cat("Filled hs_city:", before_missing - after_missing, "\n")

write_csv(df_politician_filled, here("01_data/intermediate/politicians_hs_filled.csv"))

