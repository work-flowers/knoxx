#!/usr/bin/env Rscript

library(httr2)
library(jsonlite)
library(keyring)

NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest"

# Fetch activities
activities_data <- request(paste0(BASE_URL, "/activities")) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 10) |>
  req_perform() |>
  resp_body_json()

cat("Top-level keys in activities response:\n")
print(names(activities_data))

cat("\n\nContacts in activities response:\n")
if (!is.null(activities_data$contacts)) {
  cat(sprintf("Number of contacts: %d\n\n", length(activities_data$contacts)))
  for (i in 1:min(10, length(activities_data$contacts))) {
    con <- activities_data$contacts[[i]]
    cat(sprintf("%s: %s\n", con$id %||% "NA", con$name %||% "NA"))
  }
} else {
  cat("No contacts field in response\n")
}

cat("\n\nAccounts/Leads in activities response:\n")
if (!is.null(activities_data$leads)) {
  cat(sprintf("Number of leads: %d\n", length(activities_data$leads)))
}
if (!is.null(activities_data$accounts)) {
  cat(sprintf("Number of accounts: %d\n", length(activities_data$accounts)))
}
