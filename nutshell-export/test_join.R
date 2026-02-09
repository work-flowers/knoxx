#!/usr/bin/env Rscript

library(httr2)
library(jsonlite)
library(tidyverse)
library(keyring)

NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest"

# Fetch all contacts with pagination
fetch_all_paginated <- function(endpoint, entity_name) {
  all_entities <- list()
  page <- 0
  page_limit <- 100

  repeat {
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

    if (length(entities) < page_limit) {
      break
    }

    page <- page + 1
  }

  all_entities
}

cat("Fetching all contacts...\n")
all_contacts <- fetch_all_paginated("/contacts", "contacts")
cat(sprintf("Total contacts: %d\n\n", length(all_contacts)))

# Create lookup
contacts_lookup <- map_dfr(all_contacts, function(con) {
  tibble(
    contact_id = con$id %||% NA,
    contact_name = con$name %||% NA
  )
})

cat("Looking for specific contact IDs:\n")
test_ids <- c("3-contacts", "71-contacts", "75-contacts")
for (id in test_ids) {
  match <- contacts_lookup |> filter(contact_id == id)
  if (nrow(match) > 0) {
    cat(sprintf("  %s: %s ✓\n", id, match$contact_name[1]))
  } else {
    cat(sprintf("  %s: NOT FOUND ✗\n", id))
  }
}
