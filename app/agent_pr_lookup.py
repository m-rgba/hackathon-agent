import requests
import re
import json
from datetime import datetime
from typing import Generator, Dict, List
from logger import logger
import weave

@weave.op()
def lookup_prs(github_token: str, search_data: Dict) -> Generator[str, None, None]:
    """
    Look up pull requests based on search criteria and return a generator that yields status updates and results.
    """
    try:
        # Initial status update
        yield "> Looking up pull requests...\n\n"

        # Extract search parameters
        start_date = search_data.get('start_date')
        end_date = search_data.get('end_date')
        author = search_data.get('author')
        search_term = search_data.get('search_term')

        # Log search parameters
        logger.info("Search Parameters:")
        logger.info(f"  - Start Date: {start_date}")
        logger.info(f"  - End Date: {end_date}")
        logger.info(f"  - Author: {author}")
        logger.info(f"  - Search Term: {search_term}")

        # --- Step 1: Setup GitHub API configuration ---
        graphql_url = "https://api.github.com/graphql"
        headers = {"Authorization": f"bearer {github_token}"}

        # Default to searching in the current repository
        owner = "wandb"  # This should be configurable
        repo_name = "weave"  # This should be configurable
        
        logger.info(f"Target Repository: {owner}/{repo_name}")
        yield "> Successfully configured GitHub API access\n\n"

        # --- Step 2: Build search query ---
        search_qualifiers = f"repo:{owner}/{repo_name} is:pr"

        # Add search term filter (applied to PR title and body) if provided
        if search_term:
            search_qualifiers += f' "{search_term}" in:title,body'

        # Add created date range if provided
        if start_date and end_date:
            search_qualifiers += f" created:{start_date}..{end_date}"
        elif start_date:
            search_qualifiers += f" created:>={start_date}"
        elif end_date:
            search_qualifiers += f" created:<={end_date}"

        # Add author filter if provided
        if author:
            search_qualifiers += f" author:{author}"

        logger.info(f"Search Query: {search_qualifiers}")
        yield "> Built search query with provided filters\n\n"

        # --- Step 3: Define and execute GraphQL query ---
        graphql_query = """
        query SearchPRs($query: String!) {
          search(first: 100, query: $query, type: ISSUE) {
            nodes {
              ... on PullRequest {
                title
                url
                state
                createdAt
                updatedAt
                additions
                deletions
                author {
                  ... on User {
                    login
                    name
                  }
                }
                files(first: 100) {
                  edges {
                    node {
                      path
                    }
                  }
                }
              }
            }
          }
        }
        """

        variables = {"query": search_qualifiers}
        
        # Log request details
        logger.info("GraphQL Request Details:")
        logger.info(f"  URL: {graphql_url}")
        logger.info(f"  Variables: {json.dumps(variables, indent=2)}")
        
        response = requests.post(graphql_url, json={"query": graphql_query, "variables": variables}, headers=headers)
        
        # Log response details
        logger.info(f"Response Status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"GraphQL query failed with status {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        data = response.json()
        
        # Log response data
        logger.info("Response Data:")
        logger.info(json.dumps(data, indent=2))
        
        if "errors" in data:
            logger.error(f"GraphQL Errors: {json.dumps(data['errors'], indent=2)}")
            raise Exception(f"GraphQL query returned errors: {data['errors']}")
            
        pr_nodes = data["data"]["search"]["nodes"]
        logger.info(f"PRs Found: {len(pr_nodes)}")

        # Log first few PR titles for debugging
        if pr_nodes:
            logger.info("First few PRs found:")
            for pr in pr_nodes[:3]:
                logger.info(f"  - {pr.get('title')} by {pr.get('author', {}).get('login')}")

        yield f"> Found {len(pr_nodes)} pull requests\n\n"

        # --- Step 4: Filter and format results ---
        # Look for frontend-related files
        frontend_extensions = ('.css', '.less', '.html', '.js', '.jsx', '.ts', '.tsx')
        filtered_prs = []

        for pr in pr_nodes:
            # Check if PR has frontend file changes
            files_edges = pr.get("files", {}).get("edges", [])
            has_frontend_change = any(edge["node"]["path"].lower().endswith(frontend_extensions)
                                  for edge in files_edges)
            if has_frontend_change:
                filtered_prs.append(pr)
                logger.info(f"Including PR: {pr.get('title')} (has frontend changes)")
            else:
                logger.info(f"Excluding PR: {pr.get('title')} (no frontend changes)")

        logger.info(f"Frontend PRs Found: {len(filtered_prs)}")
        yield f"> Filtered to {len(filtered_prs)} design-related pull requests\n\n"

        # --- Step 5: Generate markdown table ---
        if filtered_prs:
            markdown_table = "| Title | Author | State | Created | Changes |\n"
            markdown_table += "|---|---|---|---|---|\n"

            for pr in filtered_prs:
                author = pr.get("author") or {}
                login = author.get("login", "unknown")
                name = author.get("name", "unknown")
                title = pr["title"]
                url = pr["url"]
                created_at = datetime.fromisoformat(pr["createdAt"].replace('Z', '+00:00')).strftime('%Y-%m-%d')
                additions = pr.get("additions", 0)
                deletions = pr.get("deletions", 0)
                changes = f"+{additions}/-{deletions}"
                state = pr["state"]

                markdown_table += f"| [{title}]({url}) | {login} | {state} | {created_at} | {changes} |\n"

            yield markdown_table + "\n\n"
            yield "Your pull requests have been successfully retrieved! Let me know if you'd like to perform another search or need any other assistance."
        else:
            yield "No matching pull requests found.\n\n"

    except Exception as e:
        error_msg = f"Error during PR lookup: {str(e)}"
        logger.error(error_msg)
        yield f"Error: {error_msg}\n\n" 