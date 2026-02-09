#!/usr/bin/env Rscript

# Nutshell Activities Export with Account and Contact Names

library(httr2)
library(jsonlite)
library(tidyverse)
library(keyring)

# Get API key from keyring
NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest"

cat("=== Nutshell Activities Export ===\n\n")

# Helper function to make paginated API requests for accounts/contacts
fetch_all_paginated <- function(endpoint, entity_name) {
  all_entities <- list()
  page <- 0
  page_limit <- 100

  repeat {
    cat(sprintf("  Fetching page %d...\n", page + 1))

    resp <- request(paste0(BASE_URL, endpoint)) |>
      req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
      req_url_query(`page[limit]` = page_limit, `page[page]` = page) |>
      req_retry(max_tries = 3) |>
      req_perform() |>
      resp_body_json()

    entities <- resp[[entity_name]]

    if (is.null(entities) || length(entities) == 0) {
      break
    }

    all_entities <- c(all_entities, entities)

    # Check if we got fewer results than the limit (last page)
    if (length(entities) < page_limit) {
      break
    }

    page <- page + 1
  }

  all_entities
}

# Fetch activities (using smaller limit to avoid timeout)
cat("Fetching activities...\n")
activities_data <- request(paste0(BASE_URL, "/activities")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 500) |>
  req_retry(max_tries = 3) |>
  req_timeout(120) |>
  req_perform() |>
  resp_body_json()

activities <- activities_data$activities
cat(sprintf("  Retrieved %d activities\n", length(activities)))

if (length(activities) == 0) {
  cat("No activities found!\n")
  quit()
}

# Fetch all accounts
cat("Fetching accounts...\n")
accounts <- fetch_all_paginated("/accounts", "accounts")
cat(sprintf("  Retrieved %d total accounts\n", length(accounts)))

# Fetch all contacts
cat("Fetching contacts...\n")
contacts <- fetch_all_paginated("/contacts", "contacts")
cat(sprintf("  Retrieved %d total contacts\n\n", length(contacts)))

# Create lookup tables
accounts_lookup <- map_dfr(accounts, function(acc) {
  tibble(
    account_id = acc$id %||% NA,
    account_name = acc$name %||% NA
  )
})

contacts_lookup <- map_dfr(contacts, function(con) {
  tibble(
    contact_id = con$id %||% NA,
    contact_name = con$name %||% NA
  )
})

# Helper function to get names from IDs
get_names_from_ids <- function(ids, lookup_df, id_col, name_col) {
  if (is.null(ids) || length(ids) == 0) {
    return(NA_character_)
  }

  ids_vec <- unlist(ids)
  names <- lookup_df |>
    filter(!!sym(id_col) %in% ids_vec) |>
    pull(!!sym(name_col))

  if (length(names) == 0) {
    return(NA_character_)
  }

  paste(names, collapse = ", ")
}

# Convert activities to data frame with names
cat("Processing activities...\n")
activities_df <- map_dfr(activities, function(act) {
  tibble(
    id = act$id %||% NA,
    type = act$type %||% NA,
    name = act$name %||% NA,
    start_time = if (!is.null(act$startTime)) as.POSIXct(act$startTime, origin = "1970-01-01") else NA,
    end_time = if (!is.null(act$endTime)) as.POSIXct(act$endTime, origin = "1970-01-01") else NA,
    is_logged = act$isLogged %||% NA,
    is_cancelled = act$isCancelled %||% NA,
    agenda = act$agenda %||% NA,
    account_names = get_names_from_ids(act$links$accounts, accounts_lookup, "account_id", "account_name"),
    contact_names = get_names_from_ids(act$links$contacts, contacts_lookup, "contact_id", "contact_name"),
    num_comments = length(act$links$comments %||% list())
  )
})

# Save to CSV
output_file <- sprintf("nutshell_activities_%s.csv", format(Sys.time(), "%Y%m%d_%H%M%S"))
write_csv(activities_df, output_file)

cat(sprintf("\nSaved %d activities to %s\n", nrow(activities_df), output_file))
cat("Done!\n")
