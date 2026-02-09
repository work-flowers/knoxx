#!/usr/bin/env Rscript

library(httr2)
library(jsonlite)
library(tidyverse)
library(keyring)

NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest"

# Fetch a few activities
activities_data <- request(paste0(BASE_URL, "/activities")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 10) |>
  req_perform() |>
  resp_body_json()

# Fetch a few accounts
accounts_data <- request(paste0(BASE_URL, "/accounts")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(`page[limit]` = 10) |>
  req_perform() |>
  resp_body_json()

# Fetch a few contacts
contacts_data <- request(paste0(BASE_URL, "/contacts")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(`page[limit]` = 10) |>
  req_perform() |>
  resp_body_json()

cat("=== Activity Links ===\n")
for (i in 1:min(5, length(activities_data$activities))) {
  act <- activities_data$activities[[i]]
  cat(sprintf("\nActivity %s: %s\n", act$id, act$name))
  cat("  Account IDs:", paste(unlist(act$links$accounts), collapse = ", "), "\n")
  cat("  Contact IDs:", paste(unlist(act$links$contacts), collapse = ", "), "\n")
}

cat("\n\n=== Account IDs ===\n")
for (i in 1:min(5, length(accounts_data$accounts))) {
  acc <- accounts_data$accounts[[i]]
  cat(sprintf("%s: %s\n", acc$id, acc$name))
}

cat("\n\n=== Contact IDs ===\n")
for (i in 1:min(5, length(contacts_data$contacts))) {
  con <- contacts_data$contacts[[i]]
  cat(sprintf("%s: %s\n", con$id, con$name))
}
