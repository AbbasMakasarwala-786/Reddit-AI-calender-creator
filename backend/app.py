from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Optional
from datetime import datetime
import json
import os
from enum import Enum

# Import the existing Reddit Mastermind logic
from reddit_mastermind import (
    Persona, 
    RedditPost, 
    RedditComment, 
    GeneratedContent,
    QualityScore,
    generate_reddit_calendar
)

# ==================== API MODELS ====================

class PersonaCreate(BaseModel):
    """API model for creating personas"""
    username: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    background: str = Field(..., min_length=10, max_length=500)
    style: str = Field(..., min_length=10, max_length=300)
    expertise: str = Field(..., min_length=5, max_length=300)
    quirks: List[str] = Field(default_factory=list, max_items=10)
    posting_patterns: str = Field(default="", max_length=200)
    
    @validator('quirks')
    def validate_quirks(cls, v):
        if len(v) > 0:
            for quirk in v:
                if len(quirk) < 2 or len(quirk) > 100:
                    raise ValueError('Each quirk must be 2-100 characters')
        return v

class CalendarRequest(BaseModel):
    """Request model for generating calendar"""
    company_info: str = Field(..., min_length=50, max_length=2000, 
                              description="Detailed company information")
    personas: List[PersonaCreate] = Field(..., min_items=2, max_items=10,
                                          description="2-10 personas required")
    subreddits: List[str] = Field(..., min_items=1, max_items=20,
                                   description="Target subreddits (e.g., r/startups)")
    target_queries: List[str] = Field(..., min_items=1, max_items=30,
                                       description="Keywords/queries to target")
    posts_per_week: int = Field(..., ge=1, le=15,
                                 description="Number of posts per week (1-15)")
    week_number: int = Field(default=1, ge=1, le=52,
                             description="Week number (1-52)")
    
    @validator('subreddits')
    def validate_subreddits(cls, v):
        for sub in v:
            if not sub.startswith('r/'):
                raise ValueError(f'Subreddit must start with r/ - got: {sub}')
            if len(sub) < 4 or len(sub) > 30:
                raise ValueError(f'Subreddit name invalid length: {sub}')
        return v
    
    @validator('target_queries')
    def validate_queries(cls, v):
        for query in v:
            if len(query) < 2 or len(query) > 100:
                raise ValueError(f'Query must be 2-100 characters: {query}')
        return v

class CalendarResponse(BaseModel):
    """Response model for generated calendar"""
    calendar_id: str
    week_number: int
    generated_at: str
    posts: List[Dict]
    comments: List[Dict]
    quality_assessment: Dict
    status: str
    
class JobStatus(str, Enum):
    """Background job status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobResponse(BaseModel):
    """Response for async job status"""
    job_id: str
    status: JobStatus
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[CalendarResponse] = None
    error: Optional[str] = None

# ==================== IN-MEMORY STORAGE ====================
# In production, use Redis/PostgreSQL

jobs_db: Dict[str, JobResponse] = {}
calendars_db: Dict[str, CalendarResponse] = {}

# ==================== FASTAPI APP ====================

app = FastAPI(
    title="Reddit Mastermind API",
    description="Multi-agent system for generating authentic Reddit content calendars",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Reddit Mastermind API",
        "version": "1.0.0",
        "endpoints": {
            "docs": "/api/docs",
            "generate": "/api/calendar/generate",
            "status": "/api/calendar/status/{job_id}",
            "retrieve": "/api/calendar/{calendar_id}"
        }
    }

@app.post("/api/calendar/generate", response_model=JobResponse, status_code=202)
async def generate_calendar(
    request: CalendarRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate a Reddit content calendar (async)
    
    Returns a job_id immediately. Poll /api/calendar/status/{job_id} for results.
    """
    
    # Validate API key
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY not configured on server"
        )
    
    # Create job ID
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    
    # Initialize job
    job = JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=datetime.now().isoformat()
    )
    jobs_db[job_id] = job
    
    # Add background task
    background_tasks.add_task(
        process_calendar_generation,
        job_id=job_id,
        request=request
    )
    
    return job

async def process_calendar_generation(job_id: str, request: CalendarRequest):
    """Background task for calendar generation"""
    
    try:
        # Update status
        jobs_db[job_id].status = JobStatus.PROCESSING
        
        # Convert API models to internal models
        personas = [
            Persona(
                username=p.username,
                name=p.name,
                background=p.background,
                style=p.style,
                expertise=p.expertise,
                quirks=p.quirks,
                posting_patterns=p.posting_patterns
            )
            for p in request.personas
        ]
        
        # Generate calendar
        content = generate_reddit_calendar(
            company_info=request.company_info,
            personas=personas,
            subreddits=request.subreddits,
            target_queries=request.target_queries,
            posts_per_week=request.posts_per_week,
            week_number=request.week_number
        )
        
        # Create calendar ID
        calendar_id = f"cal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
        
        # Create response
        calendar_response = CalendarResponse(
            calendar_id=calendar_id,
            week_number=request.week_number,
            generated_at=datetime.now().isoformat(),
            posts=[p.model_dump() for p in content.posts],
            comments=[c.model_dump() for c in content.comments],
            quality_assessment=content.quality_assessment.model_dump(),
            status="completed"
        )
        
        # Store calendar
        calendars_db[calendar_id] = calendar_response
        
        # Update job
        jobs_db[job_id].status = JobStatus.COMPLETED
        jobs_db[job_id].completed_at = datetime.now().isoformat()
        jobs_db[job_id].result = calendar_response
        
    except Exception as e:
        # Handle errors
        jobs_db[job_id].status = JobStatus.FAILED
        jobs_db[job_id].completed_at = datetime.now().isoformat()
        jobs_db[job_id].error = str(e)
        print(f"❌ Job {job_id} failed: {e}")

@app.get("/api/calendar/status/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """
    Check the status of a calendar generation job
    """
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs_db[job_id]

@app.get("/api/calendar/{calendar_id}", response_model=CalendarResponse)
async def get_calendar(calendar_id: str):
    """
    Retrieve a generated calendar by ID
    """
    if calendar_id not in calendars_db:
        raise HTTPException(status_code=404, detail="Calendar not found")
    
    return calendars_db[calendar_id]

@app.get("/api/calendars", response_model=List[CalendarResponse])
async def list_calendars(limit: int = 10, offset: int = 0):
    """
    List all generated calendars (paginated)
    """
    calendars = list(calendars_db.values())
    # Sort by generated_at descending
    calendars.sort(key=lambda x: x.generated_at, reverse=True)
    
    return calendars[offset:offset + limit]

@app.post("/api/calendar/generate-next-week/{calendar_id}", response_model=JobResponse, status_code=202)
async def generate_next_week(
    calendar_id: str,
    background_tasks: BackgroundTasks
):
    """
    Generate the next week's calendar based on an existing one
    (Simulates the cron job functionality)
    """
    if calendar_id not in calendars_db:
        raise HTTPException(status_code=404, detail="Calendar not found")
    
    # This would need the original request data - in production, store it
    raise HTTPException(
        status_code=501,
        detail="Next week generation requires original request data. Store requests in DB for production use."
    )

@app.delete("/api/calendar/{calendar_id}")
async def delete_calendar(calendar_id: str):
    """Delete a calendar"""
    if calendar_id not in calendars_db:
        raise HTTPException(status_code=404, detail="Calendar not found")
    
    del calendars_db[calendar_id]
    return {"status": "deleted", "calendar_id": calendar_id}

# ==================== VALIDATION ENDPOINTS ====================

@app.post("/api/validate/personas")
async def validate_personas(personas: List[PersonaCreate]):
    """
    Validate persona configurations without generating content
    """
    issues = []
    
    # Check for duplicate usernames
    usernames = [p.username for p in personas]
    if len(usernames) != len(set(usernames)):
        issues.append("Duplicate usernames detected")
    
    # Check diversity
    expertise_areas = [p.expertise.lower() for p in personas]
    if len(set(expertise_areas)) < len(personas) * 0.5:
        issues.append("Personas lack diversity in expertise")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "persona_count": len(personas)
    }

@app.post("/api/validate/request")
async def validate_request(request: CalendarRequest):
    """
    Validate entire request without generating content
    """
    issues = []
    warnings = []
    
    # Check persona/subreddit ratio
    if len(request.subreddits) > len(request.personas) * 2:
        warnings.append("More subreddits than personas may lead to overposting")
    
    # Check posts per week ratio
    if request.posts_per_week > len(request.subreddits) * 2:
        warnings.append("High posts_per_week may appear unnatural")
    
    # Check query relevance (basic)
    if len(request.target_queries) < request.posts_per_week:
        warnings.append("Consider having more target queries than posts per week")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "estimated_generation_time": f"{request.posts_per_week * 2}-{request.posts_per_week * 4} minutes"
    }

# ==================== EXAMPLE DATA ENDPOINT ====================

@app.get("/api/examples/sample-request")
async def get_sample_request():
    """Get a sample request for testing"""
    return {
        "company_info": "Slideforge is an AI-powered presentation tool that turns outlines into polished slide decks. Users paste content, choose a style, and get structured layouts with visuals. Exports to PowerPoint, Google Slides, PDF. Has API for integrations. Target users: startup operators, consultants, sales teams, educators.",
        "personas": [
            {
                "username": "riley_ops",
                "name": "Riley Hart",
                "background": "Head of operations at SaaS startup, grew up in Colorado",
                "style": "Professional but authentic, shares personal struggles",
                "expertise": "Operations, presentations, board decks",
                "quirks": ["Miro boards", "morning runs", "color-coded folders"],
                "posting_patterns": "Posts during work hours, prefers r/startups"
            },
            {
                "username": "jordan_consults",
                "name": "Jordan Brooks",
                "background": "Independent consultant for early-stage founders",
                "style": "Thoughtful, narrative-focused, takes pride in work",
                "expertise": "Strategy, competitive analysis, storytelling",
                "quirks": ["Archive of best decks", "works at cafe"],
                "posting_patterns": "Evening poster, active in consulting communities"
            }
        ],
        "subreddits": ["r/startups", "r/consulting", "r/productivity"],
        "target_queries": ["presentation tools", "pitch deck help", "slide design tips"],
        "posts_per_week": 3,
        "week_number": 1
    }

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )