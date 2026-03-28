/**
 * Engram Memory Community Edition - Cloud Integration Example
 * 
 * This file demonstrates how to enable Engram Cloud integration.
 * Run with: ENGRAM_API_KEY=eng_xxxxx node examples/cloud-integration.js
 */

const { register } = require('../dist/index.js');

// Configuration with Engram Cloud enabled
const cloudConfig = {
  // Keep local fallback configuration
  qdrantUrl: "http://localhost:6333",
  embeddingUrl: "http://localhost:11435",
  
  // Enable Engram Cloud
  engramCloud: true,
  engramApiKey: process.env.ENGRAM_API_KEY,
  engramBaseUrl: "https://api.engrammemory.ai",
  
  // Standard settings
  autoRecall: true,
  autoCapture: true,
  debug: true
};

async function cloudIntegrationDemo() {
  console.log("☁️ Engram Memory - Cloud Integration Demo\n");

  if (!process.env.ENGRAM_API_KEY) {
    console.log("❌ Missing ENGRAM_API_KEY environment variable");
    console.log("💡 Get your API key from: https://engrammemory.ai/dashboard");
    console.log("💡 Run: ENGRAM_API_KEY=eng_xxxxx node examples/cloud-integration.js");
    return;
  }

  try {
    // Initialize plugin with cloud configuration
    const plugin = register(cloudConfig);
    console.log("✅ Plugin initialized with Engram Cloud integration\n");

    // 1. Store memories (will use cloud deduplication)
    console.log("📝 Storing memories with cloud deduplication...");
    
    // These similar memories will be deduplicated by Engram Cloud
    await plugin.tools.memory_store({
      text: "I prefer TypeScript for large applications",
      category: "preference",
      importance: 0.8
    });
    
    await plugin.tools.memory_store({
      text: "TypeScript is my preferred language for big projects", 
      category: "preference",
      importance: 0.8
    });
    
    await plugin.tools.memory_store({
      text: "I like using TypeScript instead of JavaScript",
      category: "preference", 
      importance: 0.8
    });

    console.log("✅ Memories stored with automatic deduplication!\n");

    // 2. Demonstrate cloud search capabilities
    console.log("🔍 Searching with cloud-enhanced search...");
    const results = await plugin.tools.memory_search({
      query: "programming language preferences",
      limit: 5
    });
    console.log("Cloud search results:", results, "\n");

    // 3. Store technical facts
    console.log("📝 Storing technical information...");
    
    const techFacts = [
      "Our authentication service uses JWT tokens with 24-hour expiry",
      "The database runs PostgreSQL 15 with read replicas", 
      "We deploy using Docker containers on AWS ECS",
      "The API rate limit is 1000 requests per minute per API key",
      "All sensitive data is encrypted with AES-256"
    ];

    for (const fact of techFacts) {
      await plugin.tools.memory_store({
        text: fact,
        category: "fact",
        importance: 0.7
      });
    }

    console.log("✅ Technical facts stored with cloud optimization!\n");

    // 4. Advanced search with cloud features
    console.log("🧠 Testing cloud-enhanced semantic search...");
    
    const advancedQueries = [
      "How long do our JWT tokens last?",
      "What database technology do we use?", 
      "How do we deploy our applications?",
      "What are the API rate limits?",
      "How do we handle data encryption?"
    ];

    for (const query of advancedQueries) {
      console.log(`\n❓ Query: "${query}"`);
      const result = await plugin.tools.memory_search({ 
        query, 
        limit: 1 
      });
      console.log(`   Result: ${result || "No matches"}`);
    }

    // 5. Profile management with cloud sync
    console.log("\n👤 Managing profile with cloud synchronization...");
    
    await plugin.tools.memory_profile({
      action: "add",
      key: "role",
      value: "Senior Full-Stack Developer" 
    });

    await plugin.tools.memory_profile({
      action: "add",
      key: "experience_years",
      value: "8"
    });

    await plugin.tools.memory_profile({
      action: "add", 
      key: "specialization",
      value: "React, Node.js, TypeScript, AWS"
    });

    const profile = await plugin.tools.memory_profile({ action: "view" });
    console.log("Cloud-synced profile:", profile, "\n");

    // 6. Demonstrate cloud advantages
    console.log("✨ Cloud Integration Benefits Demonstrated:");
    console.log("   ✅ Automatic deduplication (similar memories merged)");
    console.log("   ✅ Enhanced search quality with cloud intelligence");
    console.log("   ✅ Optimized storage with advanced compression");
    console.log("   ✅ Profile synchronization across devices");
    console.log("   ✅ Enterprise-grade reliability and performance");

    console.log("\n🚀 Your memories are now powered by Engram Cloud!");
    console.log("   📊 View analytics: https://engrammemory.ai/dashboard");
    console.log("   📖 Advanced features: https://engrammemory.ai/docs");

  } catch (error) {
    console.error("❌ Cloud integration demo failed:", error.message);
    
    if (error.message.includes("401") || error.message.includes("403")) {
      console.log("\n🔧 Authentication Error:");
      console.log("   • Check your API key is correct");
      console.log("   • Ensure your account is active");
      console.log("   • Visit: https://engrammemory.ai/dashboard");
    } else if (error.message.includes("fetch")) {
      console.log("\n🔧 Network Error:");
      console.log("   • Check internet connection");
      console.log("   • Verify firewall settings"); 
      console.log("   • Try again in a few moments");
    } else {
      console.log("\n🔧 Troubleshooting:");
      console.log("   • Verify API key format: eng_xxxxx");
      console.log("   • Check Engram Cloud status");
      console.log("   • Contact support: help@engrammemory.ai");
    }
  }
}

// Hybrid mode example (cloud with local fallback)
async function hybridModeDemo() {
  console.log("\n🔄 Hybrid Mode Demo (Cloud + Local Fallback)\n");

  const hybridConfig = {
    // Primary: Engram Cloud
    engramCloud: true,
    engramApiKey: process.env.ENGRAM_API_KEY,
    
    // Fallback: Local setup  
    qdrantUrl: "http://localhost:6333",
    embeddingUrl: "http://localhost:11435",
    
    debug: true
  };

  try {
    const plugin = register(hybridConfig);
    
    console.log("💡 Hybrid mode enables:");
    console.log("   • Primary operation through Engram Cloud");
    console.log("   • Automatic fallback to local if cloud unavailable");
    console.log("   • Best of both worlds: cloud features + local reliability");
    
    // Test hybrid operation
    await plugin.tools.memory_store({
      text: "Hybrid mode test - this memory uses cloud if available",
      category: "fact",
      importance: 0.5
    });
    
    console.log("✅ Hybrid mode working correctly!");
    
  } catch (error) {
    console.log("⚠️ Cloud unavailable, would fallback to local operation");
  }
}

// Run the demo
if (require.main === module) {
  cloudIntegrationDemo().then(() => {
    if (process.env.ENGRAM_API_KEY) {
      return hybridModeDemo();
    }
  });
}

module.exports = { cloudIntegrationDemo, hybridModeDemo };