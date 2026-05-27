# API
This package contains the HTTP API of our solution. In order to access the HTTP endpoints, you must enable port forwarding with
```shell
kubectl port-forward -n fission svc/router 9000:80
```

## Endpoints

### Top Voted Candidates
Get the top voted candidates to the house for the 2025 elections.

Path: `/elections/top-candidates`

Query Parameters:
- `limit`: Integer, optional, total results to return.
- `party_abbrev`: Abbreviation of a political party to limit results to that party.

Response Format:
```json
{
  "candidates": [
    {
      "candidate_given_name": "Name",
      "candidate_id": 41682,
      "candidate_surname": "SURNAME",
      "division": "PLACE",
      "party_abbreviation": "IND",
      "party_name": "Independent",
      "state": "ACT",
      "total_votes": 44930
    }
  ]
}
```

## Top Parties

Path:

Response Format
```json
{
  "parties": [
    {
      "party_abbreviation": "ALP",
      "party_name": "Australian Labor Party",
      "total_candidates": 92,
      "total_elected": 64
    }
  ]
}
```
