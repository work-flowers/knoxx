#!/usr/bin/env Rscript

# Quick script to inspect activity structure

library(httr2)
library(jsonlite)
library(keyring)

NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")
USERNAME <- "veer@knoxxfoods.com"
BASE_URL <- "https://app.nutshell.com/rest/activities"

resp <- request(BASE_URL) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 5) |>
  req_perform()

data <- resp |> resp_body_json()
activities <- data$activities

if (length(activities) > 0) {
  cat("=== First Activity Structure ===\n\n")
  cat("Top-level fields:\n")
  print(names(activities[[1]]))

  cat("\n\nType field:\n")
  print(activities[[1]]$type)

  cat("\n\nLinks field:\n")
  print(str(activities[[1]]$links))

  cat("\n\nFull first activity:\n")
  print(str(activities[[1]], max.level = 2))
}
