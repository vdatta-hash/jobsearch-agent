import os
import csv
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv("linkedin_agent.env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# Engine configuration is handled dynamically within search_linkedin_jobs using google_jobs

# --- Configuration ---
class JobSearchStrategy(BaseModel):
    analysis: str = Field(description="Brief analysis of the user's background, core strengths, and ideal seniority/roles.")
    target_domains: list[str] = Field(description="Key target domain areas deduced from the profile and preferences (e.g. ['Cloud Security', 'Customer Engineering']).")
    seniority_level: str = Field(description="Seniority tier target level (e.g. 'Director / Senior Manager').")
    target_locations: list[str] = Field(description="Hierarchical target locations (e.g. ['San Francisco Bay Area', 'United States']).")
    primary_query: str = Field(description="The single best Google Jobs search query (e.g., 'Director Cloud Security').")
    fallback_queries: list[str] = Field(description="A list of 3 to 5 alternative job titles/queries to search if the primary query yields no results.")



# ... [Keep your get_profile_summary function exactly as it was] ...

def get_profile_summary(file_path):
    try:
        profile_data = []
        with open(file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                clean_row = {k: v for k, v in row.items() if v}
                profile_data.append(str(clean_row))
        return "\n".join(profile_data)
    except FileNotFoundError:
        print(f"Error: Could not find '{file_path}'.")
        return None

def filter_management_jobs(jobs):
    management_keywords = ["manager", "director", "head", "vp", "vice president", "chief", "supervisor", "president"]
    ic_keywords = ["software engineer", "swe", "staff", "principal", "engineer iii", "engineer ii", "engineer i", "sr. engineer", "senior engineer", "individual contributor", "intern", "architect"]
    
    filtered = []
    for job in jobs:
        title = job.get("title", "").lower()
        if any(ic in title for ic in ic_keywords) and not any(mk in title for mk in management_keywords):
            continue
        if any(mk in title for mk in management_keywords):
            filtered.append(job)
    return filtered

def fetch_serpapi_jobs(query, location):
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "api_key": SERPAPI_API_KEY,
        "hl": "en",
        "gl": "us"
    }
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
        jobs = filter_management_jobs(response.json().get("jobs_results", []))
        return {"query": query, "location": location, "jobs": jobs}
    except Exception as e:
        print(f"Error fetching '{query}' in '{location}': {e}")
        return {"query": query, "location": location, "jobs": []}

import json

def search_linkedin_jobs(profile_text, preferences):
    print("Analyzing profile and generating search strategy...")
    
    prompt = ChatPromptTemplate.from_template("""
    You are an expert executive recruiter and career advisor. Analyze the following user profile:
    {profile}
    
    Take into account the following specific search preferences and constraints:
    - Target Domain: {domain}
    - Seniority Level: {seniority_level}
    - Role Constraints: {role_type}
    - Target Location: {location}
    - Optional Keywords: {optional_keywords}
    
    Based on their experience, industry specialization, leadership background, and skills:
    1. Analyze their core strengths and determine what specific roles matching the preferences fit them best.
    2. Formulate the primary job search query to find the best matching jobs.
    3. Formulate 3 to 5 alternative search queries/titles to broaden the search if needed.
    """)
    
    google_key = os.getenv("GOOGLE_API_KEY") or GOOGLE_API_KEY
    if not google_key:
        raise ValueError("GOOGLE_API_KEY is missing. Please configure it in your Environment Variables.")
        
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview", 
        google_api_key=google_key
    )
    
    structured_llm = llm.with_structured_output(JobSearchStrategy)
    chain = prompt | structured_llm
    
    strategy = chain.invoke({
        "profile": profile_text,
        "domain": preferences.get("domain"),
        "seniority_level": preferences.get("seniority_level"),
        "role_type": preferences.get("role_type"),
        "location": preferences.get("location"),
        "optional_keywords": preferences.get("optional_keywords")
    })
    
    print(f"\n--- Recruiter Analysis ---\n{strategy.analysis}\n")
    print(f"Primary Search Query: '{strategy.primary_query}'")
    
    # Define hierarchical locations to search
    primary_loc = preferences.get("location", "San Francisco Bay Area")
    search_locations = [primary_loc]
    if "united states" not in primary_loc.lower():
        search_locations.append("United States")
        
    jobs = []
    successful_loc = None
    
    # Search sequentially through each location
    for loc in search_locations:
        print(f"\nSearching in: '{loc}'...")
        
        # Formulate parallel queries to run concurrently (primary + up to 3 fallback queries)
        queries_to_check = [strategy.primary_query] + strategy.fallback_queries[:3]
        print(f"Executing concurrent SerpApi searches for queries: {queries_to_check} in '{loc}'...")
        
        loc_jobs_map = {}
        with ThreadPoolExecutor(max_workers=len(queries_to_check)) as executor:
            futures = {
                executor.submit(fetch_serpapi_jobs, q, loc): q 
                for q in queries_to_check
            }
            for future in as_completed(futures):
                res = future.result()
                q = res["query"]
                found = res["jobs"]
                if found:
                    loc_jobs_map[q] = found
                    
        # Evaluate results in order of query priority (primary query first, followed by fallbacks)
        for q in queries_to_check:
            if q in loc_jobs_map:
                jobs = loc_jobs_map[q]
                successful_loc = loc
                print(f"Success! Found {len(jobs)} management jobs in '{loc}' for query '{q}'.")
                break
                
        if jobs:
            break
            
    return {
        "analysis": strategy.analysis,
        "target_domains": strategy.target_domains,
        "seniority_level": strategy.seniority_level,
        "target_locations": strategy.target_locations,
        "primary_query": f"{strategy.primary_query} ({successful_loc or 'No match'})",
        "jobs": jobs
    }

def main():
    # Load preferences and target profile
    try:
        with open("preferences.json", "r") as pref_file:
            preferences = json.load(pref_file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading 'preferences.json': {e}")
        return

    profile_file = preferences.get("profile_file", "Profile.csv")
    profile_text = get_profile_summary(profile_file)
    if not profile_text:
        print(f"Could not load profile data from '{profile_file}'. Exiting.")
        return

    # Perform dynamic search based on LLM reasoning and user preferences
    result = search_linkedin_jobs(profile_text, preferences)
    jobs = result.get("jobs", [])

    # Output Results
    if jobs:
        print(f"\n--- Found {len(jobs)} jobs ---")
        for i, job in enumerate(jobs[:5]):
            link = (
                (job.get("apply_options", [{}])[0].get("link") if job.get("apply_options") else None) or
                job.get("share_link") or 
                job.get("job_link") or 
                "Link not available"
            )
            print(f"\nMatch {i+1}: {job.get('title')}")
            print(f"Company: {job.get('company_name')}")
            print(f"Link: {link}")
    else:
        print("No jobs found for any target titles. Try widening your location or check back later!")

if __name__ == "__main__":
    main()