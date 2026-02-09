#!/usr/bin/env Rscript

# Simple Nutshell Activities Retrieval Script

library(httr2)
library(jsonlite)
library(tidyverse)
library(keyring)

# Get API key from keyring
NUTSHELL_API_KEY <- key_get("nutshell", "veer@knoxxfoods.com")

# Configuration
BASE_URL <- "https://app.nutshell.com/rest/activities"
USERNAME <- "veer@knoxxfoods.com"

cat("=== Nutshell Activities Export ===\n\n")

# Make API request
cat("Fetching activities...\n")

resp <- request(BASE_URL) |>
  req_auth_basic(USERNAME, NUTSHELL_API_KEY) |>
  req_url_query(limit = 1100) |>
  req_perform()

cat(sprintf("Response status: %d\n", resp_status(resp)))

# Parse response
data <- resp |> resp_body_json()

# Extract activities
activities <- data$activities

cat(sprintf("Retrieved %d activities\n\n", length(activities)))

if (length(activities) == 0) {
  cat("No activities found!\n")
  quit()
}

# Helper function to flatten link arrays
flatten_links <- function(links_array) {
  if (is.null(links_array) || length(links_array) == 0) {
    return(NA_character_)
  }
  paste(unlist(links_array), collapse = ", ")
}

# Convert to data frame
activities_df <- map_dfr(activities, function(act) {
  tibble(
    id = act$id %||% NA,
    type = act$type %||% NA,
    name = act$name %||% NA,
    start_time = if (!is.null(act$startTime)) as.POSIXct(act$startTime, origin = "1970-01-01") else NA,
    end_time = if (!is.null(act$endTime)) as.POSIXct(act$endTime, origin = "1970-01-01") else NA,
    transcription = act$transcription %||% NA,
    is_logged = act$isLogged %||% NA,
    is_cancelled = act$isCancelled %||% NA,
    agenda = act$agenda %||% NA,
    links_comments = flatten_links(act$links$comments),
    links_accounts = flatten_links(act$links$accounts),
    links_contacts = flatten_links(act$links$contacts)
  )
})

# Save to CSV
output_file <- sprintf("nutshell_activities_%s.csv", format(Sys.time(), "%Y%m%d_%H%M%S"))
write_csv(activities_df, output_file)

cat(sprintf("Saved %d activities to %s\n", nrow(activities_df), output_file))
cat("Done!\n")
