// Build items array from line item inputs
const items = [];
const productCodes = bundle.inputData.product_code || [];
const quantities = bundle.inputData.quantity || [];

for (let i = 0; i < productCodes.length; i++) {
  items.push({
    "details": {
      "product": {
        "references": {
          "code": productCodes[i]
        }
      }
    },
    "measures": {
      "quantity": parseFloat(quantities[i]) || 1
    }
  });
}

// Build address object
const address = {
  "companyName": bundle.inputData.address_company || "",
  "contactName": bundle.inputData.address_contact || "",
  "street1": bundle.inputData.address_street,
  "city": bundle.inputData.address_city,
  "postcode": bundle.inputData.address_postcode,
  "state": {
    "code": bundle.inputData.address_state_code || ""
  },
  "country": {
    "iso2Code": bundle.inputData.address_country_iso2 || ""
  }
};

// Only add optional address fields if provided
if (bundle.inputData.address_street_2) {
  address.street2 = bundle.inputData.address_street_2;
}
if (bundle.inputData.address_email) {
  address.email = bundle.inputData.address_email;
}

// Build deliver object
const deliver = {
  "address": address,
  "instructions": bundle.inputData.delivery_instructions || "",
  "method": {
    "type": bundle.inputData.delivery_method_type
  }
};

// Only add requiredDate if valid YYYY-MM-DD format
if (bundle.inputData.required_date && /^\d{4}-\d{2}-\d{2}$/.test(bundle.inputData.required_date)) {
  deliver.requiredDate = bundle.inputData.required_date;
}

// Build main body
const body = {
  "references": {
    "customer": bundle.inputData.order_reference
  },
  "customer": {
    "id": bundle.inputData.customer
  },
  "details": {
    "urgent": bundle.inputData.urgent === 'true' || bundle.inputData.urgent === true,
    "instructions": bundle.inputData.packing_instructions || "",
    "deliver": deliver
  },
  "items": items
};

// Only add warehouse if provided
if (bundle.inputData.warehouse) {
  body.warehouse = { "id": bundle.inputData.warehouse };
}

// Only add collect.requiredDate if provided
if (bundle.inputData.required_ship_date && /^\d{4}-\d{2}-\d{2}$/.test(bundle.inputData.required_date)) {
  body.details.collect = {
    "requiredDate": bundle.inputData.required_date
  };
}

const options = {
  url: `https://api.cartoncloud.com/tenants/${bundle.inputData.tenant_id}/outbound-orders`,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Accept-Version': '1',
    'Authorization': `Bearer ${bundle.authData.access_token}`
  },
  body: body
};

return z.request(options)
  .then((response) => {
    return response.json;
  });