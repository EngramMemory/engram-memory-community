# Memory Persistence Examples

Real-world examples of using persistent memory with OpenClaw agents.

## Personal Assistant

### Initial Setup
```python
# Set user preferences
memory_profile("add", "communication_style", "Direct, no fluff", "static")
memory_profile("add", "timezone", "America/New_York", "static") 
memory_profile("add", "work_hours", "9am-6pm EST", "static")

# Remember important facts
memory_store("User prefers TypeScript over JavaScript for new projects", 
            category="preference", importance=0.8)

memory_store("Main project is building War Room CRM platform using Next.js + FastAPI", 
            category="fact", importance=0.9)
```

### Daily Interactions
```python
# User: "What's my communication style preference?"
memories = memory_recall("communication style preference")
# Returns: "Direct, no fluff"

# User: "What tech stack should we use for the new feature?"
memories = memory_recall("TypeScript JavaScript project preferences")
# Auto-recalls: "User prefers TypeScript over JavaScript for new projects"
```

## Software Development

### Project Documentation
```python
# Document architecture decisions
memory_store("Decided to use PostgreSQL over MongoDB for War Room due to complex relational data", 
            category="decision", importance=0.9)

memory_store("Frontend uses Tailwind CSS with custom design system, components in /components/ui/", 
            category="fact", importance=0.7)

# Track completed features
memory_store("Implemented Instagram scraper with 2FA support, handles rate limiting via account rotation", 
            category="fact", importance=0.8)
```

### Code Review & Debugging
```python
# User: "Why did we choose PostgreSQL?"
memories = memory_recall("PostgreSQL MongoDB database decision")
# Returns architectural reasoning from stored decision

# User: "How does the Instagram scraper work?"
memories = memory_recall("Instagram scraper implementation")
# Returns implementation details and features
```

## Customer Support

### Customer Profiles
```python
# Track customer preferences
memory_store("Customer ABC Corp prefers email over phone for non-urgent issues", 
            category="preference", importance=0.7)

memory_store("ABC Corp uses React + Node.js stack, has 50+ developers", 
            category="entity", importance=0.6)

# Document issue patterns  
memory_store("Billing API timeout affects 15% of enterprise customers using old SDK version", 
            category="fact", importance=0.8)
```

### Support Conversations
```python
# User: "ABC Corp is asking about integration options"
memories = memory_recall("ABC Corp preferences stack")
# Auto-recalls: Customer tech stack, communication preferences

# User: "Enterprise customer reporting billing issues"
memories = memory_recall("billing API timeout enterprise")  
# Returns known issue pattern and resolution steps
```

## Research Assistant

### Knowledge Accumulation
```python
# Save research findings
memory_store("React 18 concurrent rendering improves performance 15-30% for large lists", 
            category="fact", importance=0.8)

memory_store("Next.js 13 App Router provides better SEO and performance over Pages Router", 
            category="fact", importance=0.7)

# Track source preferences
memory_store("User values official documentation and peer-reviewed sources over blog posts", 
            category="preference", importance=0.6)
```

### Research Queries
```python
# User: "What's the performance impact of React 18?"
memories = memory_recall("React 18 performance concurrent rendering")
# Returns specific metrics from stored research

# User: "Should we upgrade to Next.js 13?"
memories = memory_recall("Next.js 13 App Router benefits")
# Provides stored comparison data
```

## Project Manager

### Team & Project Context
```python
# Document team structure
memory_store("Frontend team: Sarah (lead), Mike, Jennifer - all experienced with React", 
            category="entity", importance=0.7)

memory_store("Current sprint focused on user authentication and profile management", 
            category="fact", importance=0.8)

# Track decisions and constraints
memory_store("Decided on 2-week sprints with Friday retrospectives", 
            category="decision", importance=0.6)

memory_store("Budget constraint: must deliver MVP by end of Q2", 
            category="fact", importance=0.9)
```

### Project Planning
```python
# User: "Who should work on the authentication feature?"
memories = memory_recall("frontend team React experience authentication")
# Suggests Sarah's team based on skills and current focus

# User: "What are our timeline constraints?"
memories = memory_recall("budget deadline MVP Q2")
# Returns critical deadline information
```

## Sales Assistant

### Lead Management
```python
# Prospect information
memory_store("TechCorp Inc - SaaS company, 200 employees, currently using Salesforce", 
            category="entity", importance=0.8)

memory_store("TechCorp decision maker: Jane Smith (CTO), prefers technical demos over sales pitches", 
            category="preference", importance=0.9)

# Opportunity tracking
memory_store("TechCorp interested in API integration, budget $50k, decision timeline 6 weeks", 
            category="fact", importance=0.9)
```

### Sales Conversations
```python
# User: "Preparing for TechCorp demo tomorrow"
memories = memory_recall("TechCorp Jane Smith technical demo preferences")
# Auto-recalls decision maker preferences and context

# User: "What's TechCorp's budget and timeline?"
memories = memory_recall("TechCorp budget timeline decision")
# Returns opportunity details
```

## Content Creator

### Content Strategy
```python
# Audience insights
memory_store("Audience responds best to tutorials and behind-the-scenes content", 
            category="fact", importance=0.8)

memory_store("Technical content performs 40% better than general business posts", 
            category="fact", importance=0.7)

# Content calendar
memory_store("Publishing schedule: Tuesdays (tutorials), Thursdays (case studies), Saturdays (personal)", 
            category="decision", importance=0.6)
```

### Content Planning
```python
# User: "What content should I create this week?"
memories = memory_recall("audience tutorial behind-scenes technical")
# Suggests content types based on performance data

# User: "When should I publish the new tutorial?"
memories = memory_recall("publishing schedule Tuesday tutorial")
# Returns optimal publishing schedule
```

## Multi-Agent Scenarios

### Agent Specialization
```python
# Coding Agent (collection: "coding-agent-memory")
memory_store("Always use TypeScript for new projects", category="preference")
memory_store("API responses should be typed with Zod schemas", category="decision") 

# Design Agent (collection: "design-agent-memory")  
memory_store("Brand colors: #FF6B6B (primary), #4ECDC4 (secondary)", category="fact")
memory_store("User prefers clean, minimal designs over complex layouts", category="preference")

# Marketing Agent (collection: "marketing-agent-memory")
memory_store("Target audience: B2B SaaS companies 50-500 employees", category="fact")
memory_store("LinkedIn and email are most effective channels", category="fact")
```

### Cross-Agent Context
```python
# Shared knowledge (collection: "shared-memory")
memory_store("Current project: War Room CRM - competitive intelligence platform", 
            category="fact", importance=1.0)

memory_store("Tech stack: Next.js, FastAPI, PostgreSQL, Tailwind CSS", 
            category="fact", importance=0.9)
```

## Advanced Patterns

### Temporal Context
```python
# Track changes over time
memory_store("Q1 2024: Migrated from SQLite to PostgreSQL for scalability", 
            category="fact", importance=0.8)

memory_store("Q2 2024: Added multi-tenant support with org_id columns", 
            category="fact", importance=0.7)

# Query by time period
memories = memory_recall("database migration 2024", days_back=90)
```

### Importance-Based Filtering
```python
# High-importance memories only
critical_decisions = memory_recall("architecture decisions", min_importance=0.8)

# All preference data
user_prefs = memory_recall("preferences", category="preference")
```

### Custom Categories
```python
# Business-specific categories
memory_store("Customer churn rate dropped to 3% after onboarding improvements", 
            category="kpi", importance=0.9)

memory_store("Integration with HubSpot API requires enterprise tier subscription", 
            category="vendor_requirement", importance=0.8)

# Query custom categories
kpis = memory_recall("performance metrics", category="kpi")
vendor_info = memory_recall("API requirements", category="vendor_requirement")
```

## Performance Optimization

### Batch Operations
```python
# Store multiple related memories
facts = [
    "Frontend repository: https://github.com/company/frontend",
    "Backend repository: https://github.com/company/backend", 
    "Deployment uses Docker with Kubernetes on AWS EKS"
]

for fact in facts:
    memory_store(fact, category="infrastructure", importance=0.6)
```

### Targeted Recall
```python
# Specific, focused queries perform better than broad ones
good_query = memory_recall("React performance optimization techniques")
poor_query = memory_recall("performance")  # Too broad

# Use categories to narrow search
backend_facts = memory_recall("API design", category="fact")
frontend_prefs = memory_recall("UI frameworks", category="preference")
```

## Integration Examples

### With Other Tools
```python
# Slack integration
@app.message("remember")
def handle_remember(message):
    text = message.text.replace("remember ", "")
    memory_store(text, category="fact", importance=0.7)
    say(f"Remembered: {text}")

# Calendar integration  
def store_meeting_notes(meeting_title, notes):
    memory_store(f"Meeting '{meeting_title}': {notes}", 
                category="meeting", importance=0.8)
```

### API Integration
```python
# Store external data
def sync_customer_data(customer_id):
    crm_data = fetch_from_crm(customer_id)
    memory_store(f"Customer {customer_id}: {crm_data.summary}", 
                category="customer", importance=0.8)

# Enrich responses with memory
def enhanced_response(user_query):
    memories = memory_recall(user_query, limit=3)
    context = "\n".join([m.text for m in memories])
    return generate_response(user_query, context=context)
```

## Error Handling

### Graceful Degradation
```python
def safe_memory_recall(query, fallback="No relevant memories found"):
    try:
        memories = memory_recall(query)
        return memories if memories else [fallback]
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        return [fallback]
```

### Memory Validation
```python
def validated_memory_store(text, category="fact", importance=0.5):
    # Validate inputs
    if not text or len(text) < 10:
        raise ValueError("Memory text too short")
    
    if importance < 0 or importance > 1:
        importance = max(0, min(1, importance))
    
    # Store with validation
    return memory_store(text, category=category, importance=importance)
```

## Testing

### Memory System Tests
```python
def test_memory_persistence():
    # Store test memory
    test_fact = "Test fact for validation"
    memory_store(test_fact, category="test", importance=0.5)
    
    # Recall and verify
    results = memory_recall("test fact validation")
    assert len(results) > 0
    assert test_fact in [r.text for r in results]
    
    # Cleanup
    memory_forget("test fact validation")
```

### Performance Testing
```python
import time

def benchmark_memory_operations():
    # Test storage speed
    start = time.time()
    for i in range(100):
        memory_store(f"Benchmark test {i}", category="benchmark")
    storage_time = time.time() - start
    
    # Test recall speed  
    start = time.time()
    for i in range(100):
        memory_recall("benchmark test")
    recall_time = time.time() - start
    
    print(f"Storage: {storage_time:.2f}s, Recall: {recall_time:.2f}s")
```