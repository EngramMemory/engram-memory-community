/**
 * Engram Memory Community Edition - Basic Usage Examples
 * 
 * This file demonstrates core memory operations.
 * Run with: node examples/basic-usage.js
 */

const { register } = require('../dist/index.js');

// Initialize plugin with local configuration
const plugin = register({
  qdrantUrl: "http://localhost:6333",
  embeddingUrl: "http://localhost:11435", 
  embeddingModel: "nomic-ai/nomic-embed-text-v1.5",
  autoRecall: true,
  autoCapture: true,
  debug: true
});

async function basicUsageDemo() {
  console.log("🚀 Engram Memory Community Edition - Basic Usage Demo\n");

  try {
    // 1. Store different types of memories
    console.log("📝 Storing memories...");
    
    await plugin.tools.memory_store({ 
      text: "I prefer TypeScript over JavaScript for large projects",
      category: "preference",
      importance: 0.8
    });
    
    await plugin.tools.memory_store({
      text: "Our main API is built with FastAPI and Python 3.11",
      category: "fact",
      importance: 0.7
    });
    
    await plugin.tools.memory_store({
      text: "We decided to use React with Next.js for the frontend",
      category: "decision", 
      importance: 0.9
    });

    await plugin.tools.memory_store({
      text: "John Smith is the lead developer on the authentication service",
      category: "entity",
      importance: 0.6
    });

    console.log("✅ Memories stored successfully!\n");

    // 2. Search for memories
    console.log("🔍 Searching for programming language preferences...");
    const langResults = await plugin.tools.memory_search({ 
      query: "programming language preferences" 
    });
    console.log("Results:", langResults, "\n");

    // 3. Search with category filter
    console.log("🔍 Searching for technical decisions...");  
    const decisionResults = await plugin.tools.memory_search({
      query: "frontend technology choices",
      category: "decision"
    });
    console.log("Results:", decisionResults, "\n");

    // 4. List recent memories
    console.log("📋 Listing recent memories...");
    const recentMemories = await plugin.tools.memory_list({ limit: 5 });
    console.log("Recent memories:", recentMemories, "\n");

    // 5. Search by importance
    console.log("🔍 Searching for important memories...");
    const importantResults = await plugin.tools.memory_search({
      query: "important decisions and facts",
      minImportance: 0.7
    });
    console.log("Important memories:", importantResults, "\n");

    // 6. Profile management
    console.log("👤 Managing user profile...");
    await plugin.tools.memory_profile({
      action: "add",
      key: "timezone", 
      value: "America/New_York"
    });
    
    await plugin.tools.memory_profile({
      action: "add",
      key: "preferred_framework",
      value: "Next.js"
    });

    const profile = await plugin.tools.memory_profile({ action: "view" });
    console.log("User profile:", profile, "\n");

    // 7. Demonstrate search quality with different queries
    console.log("🧠 Testing semantic search capabilities...");
    
    const queries = [
      "What language do I like for big projects?",
      "Tell me about our API stack", 
      "Who works on authentication?",
      "What did we choose for the UI?"
    ];

    for (const query of queries) {
      console.log(`\n❓ Query: "${query}"`);
      const results = await plugin.tools.memory_search({ query, limit: 2 });
      console.log(`   Results: ${results || "No matches found"}`);
    }

    console.log("\n✨ Demo completed successfully!");

  } catch (error) {
    console.error("❌ Demo failed:", error.message);
    console.log("\n🔧 Troubleshooting:");
    console.log("   • Ensure Qdrant is running on localhost:6333");
    console.log("   • Ensure FastEmbed is running on localhost:11435");  
    console.log("   • Run: bash scripts/setup.sh");
  }
}

// Run the demo
if (require.main === module) {
  basicUsageDemo();
}

module.exports = { basicUsageDemo };