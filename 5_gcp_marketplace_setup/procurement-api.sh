# Activate SA
gcloud auth activate-service-account --key-file='<path to your service account json file>'
# List Accounts/Orders. Procurement id is typically the GCP project id
curl -L -X GET https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/accounts -H "Authorization: Bearer "$(gcloud auth print-access-token) -H "Content-Type: application/json"
# Reset Orders out for approval. Get account id from previous step
curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/accounts/209b25f0-36b9-4354-aeae-50e317f56afd:reset" -H "Authorization: Bearer $(gcloud auth print-access-token)"   -H "Content-Length: 0"

curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/entitlements/18f7b898-4024-4a2f-b9e8-520d661a8801:approve" -H "Authorization: Bearer $(gcloud auth print-access-token)"   -H "Content-Length: 0"

curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/accounts/209b25f0-36b9-4354-aeae-50e317f56afd:approve" -H "Authorization: Bearer $(gcloud auth print-access-token)"   -H "Content-Length: 0"
