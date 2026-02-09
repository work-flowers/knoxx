#!/usr/bin/env Rscript

# Debug script to see what the API actually returns

library(httr2)
library(jsonlite)
library(keyring)

NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest"

cat("=== Testing API Responses ===\n\n")

# Test accounts endpoint
cat("1. Testing /accounts endpoint\n")
accounts_resp <- request(paste0(BASE_URL, "/accounts")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(`page[limit]` = 5) |>
  req_perform() |>
  resp_body_json()

cat("Accounts response structure:\n")
cat("Top-level keys:", paste(names(accounts_resp), collapse = ", "), "\n")
if (!is.null(accounts_resp$accounts)) {
  cat("Number of accounts:", length(accounts_resp$accounts), "\n")
  if (length(accounts_resp$accounts) > 0) {
    cat("\nFirst account structure:\n")
    print(str(accounts_resp$accounts[[1]], max.level = 1))
  }
}
if (!is.null(accounts_resp$meta)) {
  cat("\nMeta info:\n")
  print(str(accounts_resp$meta, max.level = 1))
}

# Test contacts endpoint
cat("\n\n2. Testing /contacts endpoint\n")
contacts_resp <- request(paste0(BASE_URL, "/contacts")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(`page[limit]` = 5) |>
  req_perform() |>
  resp_body_json()

cat("Contacts response structure:\n")
cat("Top-level keys:", paste(names(contacts_resp), collapse = ", "), "\n")
if (!is.null(contacts_resp$contacts)) {
  cat("Number of contacts:", length(contacts_resp$contacts), "\n")
  if (length(contacts_resp$contacts) > 0) {
    cat("\nFirst contact structure:\n")
    print(str(contacts_resp$contacts[[1]], max.level = 1))
  }
}
if (!is.null(contacts_resp$meta)) {
  cat("\nMeta info:\n")
  print(str(contacts_resp$meta, max.level = 1))
}

# Test activities endpoint
cat("\n\n3. Testing /activities endpoint\n")
activities_resp <- request(paste0(BASE_URL, "/activities")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 2) |>
  req_perform() |>
  resp_body_json()

cat("Activities response structure:\n")
cat("Top-level keys:", paste(names(activities_resp), collapse = ", "), "\n")
if (!is.null(activities_resp$activities)) {
  cat("Number of activities:", length(activities_resp$activities), "\n")
  if (length(activities_resp$activities) > 0) {
    cat("\nFirst activity links:\n")
    print(str(activities_resp$activities[[1]]$links, max.level = 2))
  }
}
