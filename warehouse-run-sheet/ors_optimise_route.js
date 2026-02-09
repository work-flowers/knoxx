const startLng = bundle.inputData.start_lng;
const startLat = bundle.inputData.start_lat;
const destLngs = bundle.inputData.dest_lngs;
const destLats = bundle.inputData.dest_lats;
const destLabels = bundle.inputData.dest_labels || [];
const destIds = bundle.inputData.dest_ids || [];
const returnToStart = bundle.inputData.return_to_start;
const reverseRoute = bundle.inputData.reverse_route;

if (!startLng || !startLat || !destLngs || !destLats) {
  throw new z.errors.HaltedError('Warehouse coordinates and at least one destination are required.');
}

if (destLngs.length !== destLats.length) {
  throw new z.errors.HaltedError(
    `Mismatched inputs: ${destLngs.length} longitudes but ${destLats.length} latitudes.`
  );
}

if (destIds.length > 0 && destIds.length !== destLngs.length) {
  throw new z.errors.HaltedError(
    `Mismatched inputs: ${destIds.length} IDs but ${destLngs.length} destinations.`
  );
}

// Build jobs array - each delivery is a "job" for VROOM
const jobs = destLngs.map((lng, i) => {
  const job = {
    id: i + 1,
    location: [parseFloat(lng), parseFloat(destLats[i])]
  };
  if (destLabels[i]) {
    job.description = destLabels[i];
  }
  return job;
});

// Build vehicle - single vehicle starting (and optionally ending) at warehouse
const vehicle = {
  id: 1,
  profile: 'driving-car',
  start: [parseFloat(startLng), parseFloat(startLat)]
};

if (returnToStart) {
  vehicle.end = [parseFloat(startLng), parseFloat(startLat)];
}

const requestBody = {
  jobs: jobs,
  vehicles: [vehicle]
};

const options = {
  url: 'https://api.openrouteservice.org/optimization',
  method: 'POST',
  headers: {
    'Authorization': bundle.authData.api_key,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(requestBody),
  skipThrowForStatus: true
};

const response = await z.request(options);

if (response.status === 401 || response.status === 403) {
  throw new z.errors.RefreshAuthError('Invalid API key.');
}

if (response.status === 429) {
  throw new z.errors.Error('Rate limit exceeded. OpenRouteService allows 40 requests/minute.');
}

if (response.status >= 400) {
  const message = response.data?.error?.message || response.data?.error || JSON.stringify(response.data) || 'Unknown error';
  throw new z.errors.Error(`OpenRouteService error (${response.status}): ${message}`);
}

const data = response.data;

// Check for unassigned jobs
if (data.unassigned && data.unassigned.length > 0) {
  const unassignedIds = data.unassigned.map(u => u.id);
  z.console.log(`Warning: ${unassignedIds.length} destinations could not be assigned to the route`);
}

// Extract the optimised route
const route = data.routes[0];
const steps = route.steps || [];

// Build ordered results from the route steps
const orderedStops = [];
let stopNumber = 0;

for (const step of steps) {
  if (step.type === 'job') {
    stopNumber++;
    const jobIndex = step.job - 1; // job IDs are 1-based
    orderedStops.push({
      stop_number: stopNumber,
      job_id: step.job,
      record_id: destIds[jobIndex] || null,
      label: destLabels[jobIndex] || `Destination ${step.job}`,
      longitude: step.location[0],
      latitude: step.location[1],
      arrival_seconds: step.arrival,
      duration_to_here_seconds: step.duration,
      duration_to_here_minutes: Math.round((step.duration / 60) * 100) / 100,
      distance_to_here_metres: step.distance,
      distance_to_here_km: Math.round((step.distance / 1000) * 100) / 100
    });
  }
}

// Reverse stop order if requested (furthest-first strategy)
let totalDistance = route.distance;
let totalDuration = route.duration;

if (reverseRoute) {
  orderedStops.reverse();
  orderedStops.forEach((stop, i) => {
    stop.stop_number = i + 1;
  });

  // Call ORS Directions API to get accurate per-leg distances/durations
  const coordinates = [
    [parseFloat(startLng), parseFloat(startLat)],
    ...orderedStops.map(s => [s.longitude, s.latitude])
  ];

  if (returnToStart) {
    coordinates.push([parseFloat(startLng), parseFloat(startLat)]);
  }

  const dirOptions = {
    url: 'https://api.openrouteservice.org/v2/directions/driving-car',
    method: 'POST',
    headers: {
      'Authorization': bundle.authData.api_key,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ coordinates }),
    skipThrowForStatus: true
  };

  const dirResponse = await z.request(dirOptions);

  if (dirResponse.status === 200 && dirResponse.data?.routes?.[0]?.segments) {
    const segments = dirResponse.data.routes[0].segments;
    let cumulativeDistance = 0;
    let cumulativeDuration = 0;

    for (let i = 0; i < orderedStops.length; i++) {
      cumulativeDistance += segments[i].distance;
      cumulativeDuration += segments[i].duration;
      orderedStops[i].arrival_seconds = Math.round(cumulativeDuration);
      orderedStops[i].duration_to_here_seconds = Math.round(cumulativeDuration);
      orderedStops[i].duration_to_here_minutes = Math.round((cumulativeDuration / 60) * 100) / 100;
      orderedStops[i].distance_to_here_metres = Math.round(cumulativeDistance);
      orderedStops[i].distance_to_here_km = Math.round((cumulativeDistance / 1000) * 100) / 100;
    }

    // Update totals from the directions response
    const dirSummary = dirResponse.data.routes[0].summary;
    totalDistance = dirSummary.distance;
    totalDuration = dirSummary.duration;
  } else {
    z.console.log(`Warning: Directions API returned ${dirResponse.status}. Per-leg figures are from the original forward route.`);
  }
}

// Build the ordered labels string (arrow-separated)
const orderedLabels = orderedStops.map(s => s.label).join(' → ');

// Build comma-separated list of job IDs in optimised order
const orderedJobIds = orderedStops.map(s => s.job_id).join(',');

// Build comma-separated list of record IDs in optimised order
const orderedRecordIds = orderedStops.map(s => s.record_id).filter(Boolean).join(',');

return {
  id: Date.now(),
  total_destinations: jobs.length,
  assigned_destinations: orderedStops.length,
  unassigned_destinations: data.unassigned ? data.unassigned.length : 0,
  total_distance_metres: totalDistance,
  total_distance_km: Math.round((totalDistance / 1000) * 100) / 100,
  total_duration_seconds: totalDuration,
  total_duration_minutes: Math.round((totalDuration / 60) * 100) / 100,
  ordered_labels: orderedLabels,
  ordered_job_ids: orderedJobIds,
  ordered_record_ids: orderedRecordIds,
  return_to_start: returnToStart,
  reverse_route: reverseRoute || false,
  results: orderedStops
};