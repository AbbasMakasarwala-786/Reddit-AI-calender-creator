# Reddit Mastermind - Multi-Agent Orchestration System
# Complete backend implementation with LangChain + Groq

import os
import random  # Moved out of loop
from typing import List, Dict, Optional, Union
from datetime import datetime, timedelta
import json
import re
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableConfig  # <-- Added for typing
from langgraph.graph import StateGraph, END
import operator
from dotenv import load_dotenv
load_dotenv()

# ==================== DATA MODELS ====================

class Persona(BaseModel):
    """Persona model matching the document structure"""
    username: str
    name: str
    background: str
    style: str
    expertise: str
    quirks: List[str] = Field(default_factory=list)
    posting_patterns: str = ""

class RedditPost(BaseModel):
    """Reddit post structure"""
    post_id: str
    subreddit: str
    title: str
    body: str
    author_username: str
    timestamp: str
    keyword_ids: List[str]
    
class RedditComment(BaseModel):
    """Reddit comment structure"""
    comment_id: str
    post_id: str
    parent_comment_id: Optional[str]
    comment_text: str
    username: str
    timestamp: str
    delay_minutes: int = 0  # Delay from post/parent comment

class PostPlan(BaseModel):
    """Strategic plan for a single post"""
    subreddit: str
    target_keyword: str
    primary_persona: str
    commenting_personas: List[str]
    post_angle: str
    engagement_strategy: str
    scheduled_date: str
    scheduled_time: str

class QualityScore(BaseModel):
    """Quality assessment metrics"""
    naturalness: float = Field(ge=0, le=10, description="How human does it sound?")
    authenticity: float = Field(ge=0, le=10, description="Does it feel real?")
    engagement_potential: float = Field(ge=0, le=10, description="Will people respond?")
    subtlety: float = Field(ge=0, le=10, description="Not promotional?")
    overall_score: float = Field(ge=0, le=10)
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

class WeekPlan(BaseModel):
    """Weekly content plan"""
    week_number: int
    start_date: str
    posts: List[PostPlan]
    quality_score: Optional[float] = None

class GeneratedContent(BaseModel):
    """Final generated content"""
    posts: List[RedditPost]
    comments: List[RedditComment]
    quality_assessment: QualityScore

# ==================== STATE GRAPH ====================

class RedditState(BaseModel):
    """State for LangGraph workflow"""
    # Inputs
    company_info: str
    personas: List[Persona]
    subreddits: List[str]
    target_queries: List[str]
    posts_per_week: int
    week_number: int = 1
    
    # Planning phase
    strategic_plan: Optional[WeekPlan] = None
    plan_critique: Optional[str] = None
    
    # Generation phase
    generated_content: Optional[GeneratedContent] = None
    content_critique: Optional[str] = None
    
    # Quality control
    quality_score: Optional[QualityScore] = None
    refinement_iteration: int = 0
    max_iterations: int = 3
    
    # Final output
    final_content: Optional[GeneratedContent] = None

# ==================== AGENT PROMPTS ====================

PLANNER_PROMPT = """You are a strategic Reddit content planner. Your job is to create a posting schedule that looks COMPLETELY NATURAL and HUMAN.

COMPANY CONTEXT:
{company_info}

PERSONAS:
{personas_info}

TARGET SUBREDDITS:
{subreddits}

TARGET KEYWORDS:
{keywords}

POSTS NEEDED: {posts_per_week} posts for Week {week_number}

CRITICAL RULES FOR NATURAL CONTENT:
1. NEVER have the same persona post multiple times in the same subreddit in one week
2. Space out posts - minimum 24 hours between ANY posts
3. Match persona expertise to subreddit (don't put a student in r/consulting)
4. Questions should sound GENUINELY curious, not setup for product mentions
5. Vary the engagement patterns:
   - Some posts get 1 comment
   - Some get 2-3 comments with threading
   - NOT EVERY POST needs the full persona roster
6. Post angles should be SPECIFIC problems, not generic "what's the best tool" questions

GOOD EXAMPLES:
- "Anyone else spend way too long aligning text boxes in PowerPoint?" (relatable frustration)
- "Client wants a deck by tomorrow, any tips for fast turnaround?" (genuine time pressure)
- "What do you all use for keeping slide templates consistent across a team?" (specific need)

BAD EXAMPLES (too obvious):
- "What's the best AI presentation tool?" (sounds like market research)
- "Looking for alternatives to PowerPoint" (too generic, promotional)

OUTPUT REQUIREMENTS:
Return a JSON object with this structure:
{{
  "week_number": {week_number},
  "start_date": "YYYY-MM-DD",
  "posts": [
    {{
      "subreddit": "r/...",
      "target_keyword": "one of the target keywords",
      "primary_persona": "username",
      "commenting_personas": ["username1", "username2"],
      "post_angle": "SPECIFIC angle that sounds natural",
      "engagement_strategy": "How comments will flow naturally",
      "scheduled_date": "YYYY-MM-DD",
      "scheduled_time": "HH:MM"
    }}
  ]
}}

Think step by step:
1. Which personas fit which subreddits?
2. What would each persona ACTUALLY ask or share?
3. How can we space this out naturally?
4. Which keyword can we target WITHOUT sounding promotional?

Generate the strategic plan now:"""

CRITIC_PROMPT = """You are a quality control expert for Reddit content. Your job is to catch content that looks FAKE, PROMOTIONAL, or AI-GENERATED.

REVIEW THIS PLAN:
{plan_json}

COMPANY: {company_info}

RED FLAGS TO CHECK:
1. **Suspicious Patterns**:
   - Same personas always commenting together
   - Too many posts in one subreddit
   - Posts too close together (< 24 hours)
   - Every post gets exactly 2-3 comments (too uniform)

2. **Promotional Language**:
   - Questions that are obvious setups ("What's the BEST tool for X?")
   - Post titles that sound like market research
   - First comments that are too enthusiastic about one product
   - Missing the messy, human uncertainty

3. **Inauthenticity**:
   - Personas posting outside their expertise/background
   - Student posting in professional consulting subreddit
   - Comments that are too polished/formal for Reddit
   - Missing Reddit-specific language (abbreviations, casual tone)

4. **Engagement Unnaturalness**:
   - All conversations have perfect threading
   - No disagreements or alternative suggestions
   - Everyone agrees immediately
   - Missing the chaos of real Reddit discussions

RATING SCALE (0-10):
- 0-3: Obviously fake, would get flagged by moderators
- 4-6: Suspicious patterns, needs major revision
- 7-8: Mostly natural, minor improvements needed
- 9-10: Genuinely looks like organic Reddit activity

Provide your assessment in JSON:
{{
  "naturalness": 0-10,
  "authenticity": 0-10,
  "engagement_potential": 0-10,
  "subtlety": 0-10,
  "overall_score": 0-10,
  "issues": ["specific issue 1", "specific issue 2"],
  "suggestions": ["specific improvement 1", "specific improvement 2"]
}}

Be brutally honest. If it looks fake, say so:"""

CONTENT_GENERATOR_PROMPT = """You are generating Reddit content that MUST sound 100% human. You're writing as {persona_name}.

PERSONA DETAILS:
Name: {persona_name}
Background: {persona_background}
Style: {persona_style}
Expertise: {persona_expertise}
Quirks: {persona_quirks}

POST TO CREATE:
Subreddit: {subreddit}
Angle: {post_angle}
Target Keyword: {target_keyword}

COMPANY CONTEXT (for subtle, natural mentions only):
{company_info}

CRITICAL RULES:
1. **Write like a REAL PERSON on Reddit**:
   - Use casual language, lowercase sometimes
   - Include filler words: "tbh", "lol", "honestly", "anyone else?"
   - Real humans make typos occasionally (but don't overdo it)
   - Use Reddit abbreviations: "imo", "fwiw", "afaik"

2. **Show uncertainty and vulnerability**:
   - "I'm probably overthinking this but..."
   - "Not sure if this is the right place to ask..."
   - "Maybe I'm just bad at this lol"

3. **Be specific, not generic**:
   - BAD: "I need presentation software"
   - GOOD: "I keep spending 2 hours just fixing bullet point alignment in PowerPoint"

4. **Product mentions MUST feel accidental**:
   - NEVER in the original post (unless asking for comparison)
   - Only in comments, and only if genuinely relevant
   - Mixed with other suggestions
   - Presented with caveats: "I've been using X, not perfect but helps with Y"

5. **Match the subreddit culture**:
   - r/consulting: more professional, war stories
   - r/startups: scrappy, time-crunched
   - r/teachers: exhausted, resource-sharing
   - r/productivity: optimization-focused

EXAMPLE OF GOOD REDDIT POST (NOT YOUR PERSONA):
Title: "Does anyone else hate making slides or is it just me"
Body: "I run ops at a startup and somehow became the deck person. Every board meeting I'm up til midnight fixing alignment and font sizes. There has to be a better way to do this. What do you all do to make this process less painful?"

OUTPUT FORMAT (JSON):
{{
  "title": "natural reddit title",
  "body": "natural reddit body text (100-250 words)",
  "reasoning": "why this sounds authentic"
}}

Now generate the post for {persona_name}:"""

COMMENT_GENERATOR_PROMPT = """You are generating Reddit comments that sound 100% NATURAL and HUMAN.

ORIGINAL POST:
Title: {post_title}
Body: {post_body}
Author: {post_author}

YOU ARE: {commenter_name}
Your Background: {commenter_background}
Your Style: {commenter_style}

PARENT COMMENT (if replying to another comment):
{parent_comment}

COMPANY CONTEXT:
{company_info}

COMMENT STRATEGY:
{engagement_strategy}

CRITICAL RULES FOR NATURAL COMMENTS:

1. **Real Reddit behavior**:
   - Sometimes just "+1" or "same here"
   - Sometimes longer, story-based responses
   - Use upvote language: "this is the answer"
   - Reference your own experience: "I do something similar..."

2. **Varied engagement types**:
   - Agreement: "exactly this", "yep", "+1"
   - Addition: "also try X", "one thing that helped me..."
   - Question: "curious, have you tried Y?"
   - Story: "similar thing happened to me when..."

3. **Product mentions (if appropriate)**:
   - ONLY if genuinely relevant to the discussion
   - Buried in longer comment, not the main point
   - With caveats: "still figuring it out but", "not perfect but"
   - Mixed with other suggestions/context

4. **Threading behavior**:
   - First comment: usually longer, adds value
   - Replies: can be shorter, more casual
   - Late replies: might just validate previous comments

5. **Authenticity markers**:
   - Lowercase start sometimes
   - Contractions: "I'm", "you're", "it's"
   - Hedging: "might be wrong but", "fwiw", "ymmv"
   - Reddit slang: "tbh", "ngl", "lol", "lmao"

BAD COMMENT (too promotional):
"You should definitely try Slideforge! It's the best AI presentation tool and will solve all your problems. It has amazing features like..."

GOOD COMMENT (natural mention):
"I feel this so hard. I started using Slideforge a few weeks ago after someone here mentioned it. Still tweaking stuff after but beats staring at blank slides for an hour. Also helps to outline everything in a doc first before touching slides."

OUTPUT FORMAT (JSON):
{{
  "comment_text": "natural reddit comment",
  "delay_minutes": 15-360 (realistic time between post and comment),
  "engagement_type": "agreement|addition|story|question",
  "reasoning": "why this sounds natural"
}}

Generate the comment now:"""

FINAL_CRITIC_PROMPT = """You are doing FINAL quality assurance on generated Reddit content.

GENERATED CONTENT:
Posts: {posts_json}
Comments: {comments_json}

Analyze the ENTIRE conversation flow:

1. **Conversation Naturalness**:
   - Do the comments flow like real Reddit discussions?
   - Are there any obvious "setup and payoff" patterns?
   - Do people sound like different humans or the same AI?

2. **Timing Realism**:
   - Are comment delays realistic?
   - Do people respond too quickly (suspicious)?
   - Is there natural spacing?

3. **Language Diversity**:
   - Does each persona have distinct voice?
   - Varied sentence structures?
   - Different levels of formality?

4. **Promotional Balance**:
   - How many times is the company mentioned?
   - Do mentions feel forced?
   - Are there other brands/tools mentioned for authenticity?

5. **Reddit Culture**:
   - Proper use of Reddit slang?
   - Appropriate level of casualness?
   - Any language that screams "AI wrote this"?

AI RED FLAGS:
- "As an AI assistant"
- "It's important to note"
- "Delve into"
- "Navigate the landscape"
- Overly perfect grammar everywhere
- No typos or casual language
- All sentences same length
- Corporate buzzwords

Rate each dimension 0-10 and provide JSON:
{{
  "naturalness": 0-10,
  "authenticity": 0-10,
  "engagement_potential": 0-10,
  "subtlety": 0-10,
  "overall_score": 0-10,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["fix 1", "fix 2"]
}}

Be harsh. If something looks AI-generated, flag it:"""

# ==================== LLM SETUP ====================

def get_llm(temperature: float = 0.7) -> ChatGroq:
    """Initialize Groq LLM"""
    return ChatGroq(
        temperature=temperature,
        model_name="llama-3.3-70b-versatile",  # or mixtral-8x7b-32768
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

# ==================== AGENT FUNCTIONS ====================

def planner_agent(state: Dict, config: RunnableConfig | None = None) -> Dict:
    """Strategic planning agent"""
    print("\n🎯 PLANNER AGENT: Creating strategic content plan...")
    print(f"DEBUG: Incoming state keys: {list(state.keys())}")  # Debug
    print(f"DEBUG: company_info present? {'company_info' in state}")
    
    llm = get_llm(temperature=0.8)
    
    # Format personas for prompt
    personas_info = "\n\n".join([
        f"Username: {p.username}\n"
        f"Name: {p.name}\n"
        f"Background: {p.background}\n"
        f"Style: {p.style}\n"
        f"Expertise: {p.expertise}"
        for p in state['personas']
    ])
    
    prompt = ChatPromptTemplate.from_template(PLANNER_PROMPT)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "company_info": state['company_info'],
            "personas_info": personas_info,
            "subreddits": "\n".join(state['subreddits']),
            "keywords": "\n".join(state['target_queries']),
            "posts_per_week": state['posts_per_week'],
            "week_number": state['week_number']
        })
        
        week_plan = WeekPlan(**result)
        print(f"✅ Generated plan with {len(week_plan.posts)} posts")
        
        return {**state, "strategic_plan": week_plan}  # <-- Spread state to preserve!
        
    except Exception as e:
        print(f"❌ Planner failed: {e}")
        return {**state}  # Preserve on error
        raise

def plan_critic_agent(state: Dict, config: RunnableConfig | None = None) -> Dict:
    """Critique the strategic plan"""
    print("\n🔍 CRITIC AGENT: Reviewing strategic plan...")
    print(f"DEBUG: Incoming state keys: {list(state.keys())}")  # <-- Added debug
    print(f"DEBUG: company_info value: {state.get('company_info', 'MISSING')}")
    
    llm = get_llm(temperature=0.3)
    
    plan_json = state['strategic_plan'].model_dump_json(indent=2)
    
    prompt = ChatPromptTemplate.from_template(CRITIC_PROMPT)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "plan_json": plan_json,
            "company_info": state['company_info']
        })
        
        quality = QualityScore(**result)
        print(f"📊 Quality Score: {quality.overall_score}/10")
        
        if quality.issues:
            print(f"⚠️  Issues found: {len(quality.issues)}")
            for issue in quality.issues:
                print(f"   - {issue}")
        
        return {  # <-- Spread state
            **state,
            "quality_score": quality,
            "plan_critique": json.dumps(result)
        }
        
    except Exception as e:
        print(f"❌ Critic failed: {e}")
        return {**state}  # Preserve on error
        raise

def should_refine_plan(state: Dict, config: RunnableConfig | None = None) -> str:
    """Decide if plan needs refinement"""
    print(f"DEBUG: Conditional - keys: {list(state.keys())}")  # Debug
    if state['quality_score'].overall_score >= 7.5:
        return "generate_content"
    elif state['refinement_iteration'] >= state['max_iterations']:
        print("⚠️  Max iterations reached, proceeding anyway")
        return "generate_content"
    else:
        print(f"🔄 Refinement needed (iteration {state['refinement_iteration'] + 1})")
        return "refine_plan"

def refine_plan_agent(state: Dict, config: RunnableConfig | None = None) -> Dict:
    """Refine plan based on critique"""
    print("\n🔧 REFINE AGENT: Improving plan based on feedback...")
    print(f"DEBUG: Incoming state keys: {list(state.keys())}")  # Debug
    
    llm = get_llm(temperature=0.8)
    
    refine_prompt = f"""The strategic plan has issues. Refine it based on this feedback:

ISSUES:
{json.dumps(state['quality_score'].issues, indent=2)}

SUGGESTIONS:
{json.dumps(state['quality_score'].suggestions, indent=2)}

ORIGINAL PLAN:
{state['strategic_plan'].model_dump_json(indent=2)}

Create an improved plan following the same JSON structure. Fix the issues while maintaining naturalness."""
    
    prompt = ChatPromptTemplate.from_template(refine_prompt)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({})
        week_plan = WeekPlan(**result)
        
        return {  # <-- Spread state
            **state,
            "strategic_plan": week_plan,
            "refinement_iteration": state['refinement_iteration'] + 1
        }
        
    except Exception as e:
        print(f"❌ Refinement failed: {e}")
        return {**state, "refinement_iteration": state['refinement_iteration'] + 1}

def content_generator_agent(state: Dict, config: RunnableConfig | None = None) -> Dict:
    """Generate actual posts and comments"""
    print("\n✍️  CONTENT GENERATOR: Creating posts and comments...")
    print(f"DEBUG: Incoming state keys: {list(state.keys())}")  # Debug
    
    llm = get_llm(temperature=0.9)  # Higher temp for creativity
    
    posts = []
    comments = []
    
    plan = state['strategic_plan']
    personas_dict = {p.username: p for p in state['personas']}
    
    for i, post_plan in enumerate(plan.posts):
        print(f"\n  Generating post {i+1}/{len(plan.posts)} in {post_plan.subreddit}...")
        
        # Generate post
        primary_persona = personas_dict[post_plan.primary_persona]
        
        post_prompt = ChatPromptTemplate.from_template(CONTENT_GENERATOR_PROMPT)
        post_chain = post_prompt | llm | JsonOutputParser()
        
        try:
            post_result = post_chain.invoke({
                "persona_name": primary_persona.username,
                "persona_background": primary_persona.background,
                "persona_style": primary_persona.style,
                "persona_expertise": primary_persona.expertise,
                "persona_quirks": ", ".join(primary_persona.quirks) if primary_persona.quirks else "natural, human",
                "subreddit": post_plan.subreddit,
                "post_angle": post_plan.post_angle,
                "target_keyword": post_plan.target_keyword,
                "company_info": state['company_info']
            })
            
            # Create post object
            post_time = datetime.strptime(
                f"{post_plan.scheduled_date} {post_plan.scheduled_time}",
                "%Y-%m-%d %H:%M"
            )
            
            post = RedditPost(
                post_id=f"P{i+1}",
                subreddit=post_plan.subreddit,
                title=post_result['title'],
                body=post_result['body'],
                author_username=primary_persona.username,
                timestamp=post_time.strftime("%Y-%m-%d %H:%M"),
                keyword_ids=[post_plan.target_keyword]
            )
            posts.append(post)
            print(f"    ✅ Post created: {post.title[:50]}...")
            
            # Generate comments
            for j, commenter_username in enumerate(post_plan.commenting_personas):
                commenter = personas_dict[commenter_username]
                
                # Determine parent comment
                parent_comment_text = None
                parent_comment_id = None
                
                if j > 0 and len(comments) > 0:
                    # Sometimes reply to previous comment (threading)
                    if len([c for c in comments if c.post_id == post.post_id]) > 0:
                        if random.random() > 0.5:  # 50% chance to thread
                            previous_comments = [c for c in comments if c.post_id == post.post_id]
                            parent = previous_comments[-1]
                            parent_comment_text = parent.comment_text
                            parent_comment_id = parent.comment_id
                
                comment_prompt = ChatPromptTemplate.from_template(COMMENT_GENERATOR_PROMPT)
                comment_chain = comment_prompt | llm | JsonOutputParser()
                
                try:
                    comment_result = comment_chain.invoke({
                        "post_title": post.title,
                        "post_body": post.body,
                        "post_author": post.author_username,
                        "commenter_name": commenter.username,
                        "commenter_background": commenter.background,
                        "commenter_style": commenter.style,
                        "parent_comment": parent_comment_text or "None (top-level comment)",
                        "company_info": state['company_info'],
                        "engagement_strategy": post_plan.engagement_strategy
                    })
                    
                    # Calculate comment timestamp
                    comment_time = post_time + timedelta(minutes=comment_result.get('delay_minutes', 30))
                    
                    comment = RedditComment(
                        comment_id=f"C{len(comments)+1}",
                        post_id=post.post_id,
                        parent_comment_id=parent_comment_id,
                        comment_text=comment_result['comment_text'],
                        username=commenter.username,
                        timestamp=comment_time.strftime("%Y-%m-%d %H:%M"),
                        delay_minutes=comment_result.get('delay_minutes', 30)
                    )
                    comments.append(comment)
                    print(f"    ✅ Comment {j+1} by {commenter.username}")
                    
                except Exception as e:
                    print(f"    ⚠️  Comment generation failed: {e}")
                    continue
            
        except Exception as e:
            print(f"    ❌ Post generation failed: {e}")
            continue
    
    generated_content = GeneratedContent(
        posts=posts,
        comments=comments,
        quality_assessment=QualityScore(
            naturalness=0,
            authenticity=0,
            engagement_potential=0,
            subtlety=0,
            overall_score=0
        )
    )
    
    return {**state, "generated_content": generated_content}  # <-- Spread state

def final_critic_agent(state: Dict, config: RunnableConfig | None = None) -> Dict:
    """Final quality check on generated content"""
    print("\n🔍 FINAL CRITIC: Assessing generated content...")
    print(f"DEBUG: Incoming state keys: {list(state.keys())}")  # Debug
    
    llm = get_llm(temperature=0.2)
    
    content = state['generated_content']
    posts_json = json.dumps([p.model_dump() for p in content.posts], indent=2)
    comments_json = json.dumps([c.model_dump() for c in content.comments], indent=2)
    
    prompt = ChatPromptTemplate.from_template(FINAL_CRITIC_PROMPT)
    chain = prompt | llm | JsonOutputParser()
    
    try:
        result = chain.invoke({
            "posts_json": posts_json,
            "comments_json": comments_json
        })
        
        quality = QualityScore(**result)
        print(f"\n📊 FINAL QUALITY SCORE: {quality.overall_score}/10")
        print(f"   Naturalness: {quality.naturalness}/10")
        print(f"   Authenticity: {quality.authenticity}/10")
        print(f"   Engagement: {quality.engagement_potential}/10")
        print(f"   Subtlety: {quality.subtlety}/10")
        
        if quality.issues:
            print(f"\n⚠️  Issues found:")
            for issue in quality.issues:
                print(f"   - {issue}")
        
        content.quality_assessment = quality
        
        return {  # <-- Spread state
            **state,
            "final_content": content,
            "content_critique": json.dumps(result)
        }
        
    except Exception as e:
        print(f"❌ Final critic failed: {e}")
        return {**state, "final_content": state['generated_content']}

# ==================== WORKFLOW GRAPH ====================

def build_workflow() -> StateGraph:
    """Build the LangGraph workflow"""
    
    workflow = StateGraph(dict)
    
    # Add nodes
    workflow.add_node("planner", planner_agent)
    workflow.add_node("plan_critic", plan_critic_agent)
    workflow.add_node("refine_plan", refine_plan_agent)
    workflow.add_node("generate_content", content_generator_agent)
    workflow.add_node("final_critic", final_critic_agent)
    
    # Add edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "plan_critic")
    workflow.add_conditional_edges(
        "plan_critic",
        should_refine_plan,
        {
            "refine_plan": "refine_plan",
            "generate_content": "generate_content"
        }
    )
    workflow.add_edge("refine_plan", "plan_critic")
    workflow.add_edge("generate_content", "final_critic")
    workflow.add_edge("final_critic", END)
    
    return workflow.compile()

# ==================== MAIN EXECUTION ====================

def generate_reddit_calendar(
    company_info: str,
    personas: List[Persona],
    subreddits: List[str],
    target_queries: List[str],
    posts_per_week: int,
    week_number: int = 1
) -> GeneratedContent:
    """Main function to generate Reddit content calendar"""
    
    print("="*60)
    print("🚀 REDDIT MASTERMIND - Multi-Agent System")
    print("="*60)
    
    # Initialize state
    initial_state = {
        "company_info": company_info,
        "personas": personas,
        "subreddits": subreddits,
        "target_queries": target_queries,
        "posts_per_week": posts_per_week,
        "week_number": week_number,
        "refinement_iteration": 0,
        "max_iterations": 2  # Consistent with usage
    }
    
    # Build and run workflow
    app = build_workflow()
    
    try:
        final_state = app.invoke(initial_state)
        
        print("\n" + "="*60)
        print("✅ GENERATION COMPLETE!")
        print("="*60)
        
        return final_state['final_content']
        
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        raise

# ==================== EXAMPLE USAGE ====================

if __name__ == "__main__":
    # Parse personas from the document
    personas = [
        Persona(
            username="riley_ops",
            name="Riley Hart",
            background="Head of operations at SaaS startup, grew up in Colorado",
            style="Professional but authentic, shares personal struggles",
            expertise="Operations, presentations, board decks",
            quirks=["Miro boards", "morning runs", "color-coded folders", "comic-strip thinking"]
        ),
        Persona(
            username="jordan_consults",
            name="Jordan Brooks",
            background="Independent consultant for early-stage founders, Black family in Maryland",
            style="Thoughtful, narrative-focused, takes pride in work",
            expertise="Strategy, competitive analysis, storytelling",
            quirks=["Keeps archive of best decks", "works at cafe", "notebook for slow ideas"]
        ),
        Persona(
            username="emily_econ",
            name="Emily Chen",
            background="Economics major at state university, Taiwanese American",
            style="Student, practical, exhausted but dedicated",
            expertise="Academic presentations, research, group projects",
            quirks=["Google Doc outlines first", "library quiet floor", "reusable charts folder"]
        )
    ]
    
    company_info = """Slideforge is an AI-powered presentation tool that turns outlines into polished slide decks. 
    Users paste content, choose a style, and get structured layouts with visuals. 
    Exports to PowerPoint, Google Slides, PDF. Has API for integrations.
    Target users: startup operators, consultants, sales teams, educators."""
    
    subreddits = [
        "r/startups",
        "r/consulting", 
        "r/productivity",
        "r/PowerPoint"
    ]
    
    target_queries = [
        "presentation tools",
        "pitch deck help",
        "slide design tips",
        "PowerPoint alternatives"
    ]
    
    # Generate content
    content = generate_reddit_calendar(
        company_info=company_info,
        personas=personas,
        subreddits=subreddits,
        target_queries=target_queries,
        posts_per_week=3,
        week_number=1
    )
    
    # Export to JSON
    output = {
        "posts": [p.model_dump() for p in content.posts],
        "comments": [c.model_dump() for c in content.comments],
        "quality_score": content.quality_assessment.model_dump()
    }
    
    with open("reddit_calendar_week1.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n📁 Saved to reddit_calendar_week1.json")
    print(f"📊 Generated {len(content.posts)} posts with {len(content.comments)} comments")
    print(f"⭐ Quality Score: {content.quality_assessment.overall_score}/10")