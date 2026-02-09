const addresses = bundle.inputData.address;
const cities = bundle.inputData.city;
const regionCodes = bundle.inputData.region_code || [];
const postcodes = bundle.inputData.postcode || [];
const countries = bundle.inputData.country || [];
const ids = bundle.inputData.ids || [];

if (!addresses || !cities || addresses.length === 0 || cities.length === 0) {
  throw new z.errors.HaltedError('At least one Street Address and City is required.');
}

if (addresses.length !== cities.length) {
  throw new z.errors.HaltedError(
    `Mismatched inputs: ${addresses.length} addresses but ${cities.length} cities.`
  );
}

if (ids.length > 0 && ids.length !== addresses.length) {
  throw new z.errors.HaltedError(
    `Mismatched inputs: ${ids.length} IDs but ${addresses.length} addresses.`
  );
}

const results = [];

for (let i = 0; i < addresses.length; i++) {
  const searchParts = [addresses[i], cities[i]];
  if (postcodes[i]) searchParts.push(postcodes[i]);
  if (countries[i]) searchParts.push(countries[i]);

  const params = new URLSearchParams({
    text: searchParts.join(', '),
    size: '1'
  });

  if (countries[i]) {
    params.append('boundary.country', countries[i]);
  }

  const options = {
    url: `https://api.openrouteservice.org/geocode/search?${params.toString()}`,
    method: 'GET',
    headers: {
      'Authorization': bundle.authData.api_key
    },
    skipThrowForStatus: true
  };

  const response = await z.request(options);

  if (response.status === 401 || response.status === 403) {
    throw new z.errors.RefreshAuthError('Invalid API key.');
  }

  if (response.status === 429) {
    throw new z.errors.Error(
      `Rate limit exceeded on address ${i + 1}. OpenRouteService allows 40 requests/minute.`
    );
  }

  if (response.status === 404 || !response.data?.features?.length) {
    results.push({
      index: i,
      record_id: ids[i] || null,
      input_address: addresses[i],
      label: null,
      longitude: null,
      latitude: null,
      confidence: 0,
      matched: false
    });
    continue;
  }

  if (response.status >= 400) {
    const message = response.data?.error?.message || 'Unknown error';
    throw new z.errors.Error(`OpenRouteService error (${response.status}): ${message}`);
  }

  const feature = response.data.features[0];
  results.push({
    index: i,
    record_id: ids[i] || null,
    input_address: addresses[i],
    label: feature.properties.label,
    longitude: feature.geometry.coordinates[0],
    latitude: feature.geometry.coordinates[1],
    confidence: feature.properties.confidence,
    country: feature.properties.country,
    region: feature.properties.region,
    locality: feature.properties.locality,
    postalcode: feature.properties.postalcode,
    matched: true
  });
}

return {
  id: Date.now(),
  total_addresses: results.length,
  matched_count: results.filter(r => r.matched).length,
  unmatched_count: results.filter(r => !r.matched).length,
  results: results
};