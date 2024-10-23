

import os
import jwt  # External package
import time
import requests  # External package
from datetime import datetime, timezone

# Endpoint URL
GRAPHQL_URL = 'https://dev-federated-graphql-api.omnivoltaic.com/graphql'

# Credentials for login
EMAIL = 'dennis_njogu@omnivoltaic.com'
PASSWORD = 'D3nn1s@123'

# Token file path
TOKEN_FILE = 'token.txt'

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as file:
            return file.read().strip()
    return None

def save_token(token):
    with open(TOKEN_FILE, 'w') as file:
        file.write(token)

def is_token_expired(token):
    try:
        # Decode the token without verification to get the expiration time
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get('exp')
        if exp:
            # Check if the token is expired
            return exp < time.time()
        else:
            # Token doesn't have an expiration time
            return True
    except jwt.DecodeError:
        # Token is invalid
        return True

def get_new_token():
    headers = {
        'Content-Type': 'application/json'
    }
    # GraphQL mutation for signing in
    query = '''
    mutation SignInLoginUser($signInCredentials: SignInCredentialsDto!) {
      signInUser(signInCredentials: $signInCredentials) {
        accessToken
        __typename
      }
    }
    '''
    variables = {
        "signInCredentials": {
            "email": EMAIL,
            "password": PASSWORD
        }
    }
    response = requests.post(
        GRAPHQL_URL,
        json={'query': query, 'variables': variables},
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print('Login failed with errors:', data['errors'])
            raise Exception('Failed to obtain new token')
        # Extract the accessToken from the response
        token = data['data']['signInUser']['accessToken']
        if token:
            save_token(token)
            return token
    else:
        print(f'Login failed with status code {response.status_code}')
    raise Exception('Failed to obtain new token')

def get_latest_batch(token):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    query = """
fragment ItemSKU on ItemSKU {
  _id
  deleteStatus
  deleteAt
  createdAt
  updatedAt
  type
  actionScope
  actorName
  profile
  skuName
  productBase
  oemDescription
  properties {
    name
    attributes {
      prop
      value
      meta
      __typename
    }
    __typename
  }
  __typename
}

fragment ItemBatch on ItemBatch {
  _id
  deleteStatus
  deleteAt
  createdAt
  updatedAt
  type
  actionScope
  actionProgress
  actorName
  profile
  batchNumber
  batchDate
  description
  batchState
  starting_code
  secret_key
  code_gen_type
  itemSKU {
    ...ItemSKU
    __typename
  }
  __typename
}

fragment ItemBatchEdge on ItemBatchEdge {
  cursor
  node {
    ...ItemBatch
    __typename
  }
  __typename
}

fragment ItemBatchPageInfo on ItemBatchPageInfo {
  startCursor
  endCursor
  hasPreviousPage
  hasNextPage
  __typename
}

fragment ItemBatchConnection on ItemBatchConnection {
  edges {
    ...ItemBatchEdge
    __typename
  }
  pageInfo {
    ...ItemBatchPageInfo
    __typename
  }
  __typename
}

fragment PageData on PageData {
  count
  limit
  offset
  __typename
}

fragment GetAllItemBatchesResponse on GetAllItemBatchesResponse {
  page {
    ...ItemBatchConnection
    __typename
  }
  pageData {
    ...PageData
    __typename
  }
  __typename
}

query GetAllItemBatches($queryorder: QueryOrder!, $before: String, $after: String, $first: Int, $last: Int, $search: String) {
  getAllItemBatches(
    before: $before
    after: $after
    first: $first
    last: $last
    queryorder: $queryorder
    search: $search
  ) {
    ...GetAllItemBatchesResponse
    __typename
  }
}

    """
    variables = {
        "first": 1,
        "queryorder": "DESC"
    }
    response = requests.post(
        GRAPHQL_URL,
        json={'query': query, 'variables': variables},
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print('GraphQL query failed with errors:', data['errors'])
            return None
        else:
            # Extract the latest batch
            batches = data['data']['getAllItemBatches']['page']['edges']
            if batches:
                latest_batch = batches[0]['node']
                return latest_batch
            else:
                print('No batches found')
                return None
    else:
        print(f'GraphQL query failed with status code {response.status_code}')
        return None

def check_and_retry_actions(batch, token):
    action_progress = batch.get('actionProgress', {})
    print(action_progress)
    current_time = time.time()
    actions_to_check = ['batchCode', 'batchInitialize']
    for action_name in actions_to_check:
        action = action_progress.get(action_name)
        if action is None:
            print(f"Action '{action_name}' is not present in actionProgress.")
            continue  # Skip to the next action
        if action and action.get('state') == 'InProgress':
            print(action, "Action---510---")
            updated_on_str = action.get('updatedOn')
            if updated_on_str:
                # Parse the date string using datetime.strptime
                print(updated_on_str, "Updated On------514----")
                try:
                    # Adjust the format string to match your date format
                    updated_on = datetime.strptime(updated_on_str, '%Y-%m-%dT%H:%M:%S.%fZ')
                    print(updated_on, "Updated On")
                    updated_on_timestamp = updated_on.replace(tzinfo=timezone.utc).timestamp()
                    print(updated_on_timestamp, "Updated On TimeStamp")
                    time_diff = current_time - updated_on_timestamp

                    print(time_diff, "Time Diff")
                    if time_diff > 5 * 60:  # 5 minutes
                        print(f"Action '{action_name}' is in progress and hasn't been updated for over 5 minutes.")
                        # Call the appropriate mutation to retry the action
                        if action_name == 'batchCode':
                            retry_batch_code(batch['_id'], token)
                        elif action_name == 'batchInitialize':
                            retry_batch_initialize(batch['_id'], token)
                except ValueError as e:
                    print(f"Error parsing date string '{updated_on_str}': {e}")

def retry_batch_code(batch_id, token):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    mutation = """
mutation BatchCode($batchId: ID!, $codeDays: Int!) {
  batchCode(batchCodeInput: {batchId: $batchId, codeDays: $codeDays}) {
    batchCodes {
      codeGenerator
      itemId
      __typename
    }
    __typename
  }
}
    """
    variables = {
        "codeGenerationInput": {
            "codeDays": 1,
            "batchId": batch_id
        }
    }
    response = requests.post(
        GRAPHQL_URL,
        json={'query': mutation, 'variables': variables},
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print('GenerateCodes mutation failed with errors:', data['errors'])
        else:
            print('Successfully retried batchCode action.')
    else:
        print(f'GenerateCodes mutation failed with status code {response.status_code}')

def retry_batch_initialize(batch_id, token):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    mutation = """
mutation BatchInitialize($batchInitializeInput: BatchInitializeInput!) {
  batchInitialize(batchInitializeInput: $batchInitializeInput) {
    _id
    __typename
  }
}

    """
    variables = {
        "batchInitializeInput": {
            "itembatchId": batch_id,
            "codeGenType": None
        }
    }
    response = requests.post(
        GRAPHQL_URL,
        json={'query': mutation, 'variables': variables},
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print('BatchInitialize mutation failed with errors:', data['errors'])
        else:
            print('Successfully retried batchInitialize action.')
    else:
        print(f'BatchInitialize mutation failed with status code {response.status_code}')

def main():
    token = load_token()
    if not token or is_token_expired(token):
        print('Token is missing or expired. Obtaining new token...')
        token = get_new_token()
    else:
        print('Using existing valid token.')

    latest_batch = get_latest_batch(token)
    if latest_batch:
        check_and_retry_actions(latest_batch, token)

if __name__ == '__main__':
    main()
