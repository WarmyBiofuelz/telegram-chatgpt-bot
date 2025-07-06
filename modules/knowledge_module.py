import os
import logging
import re
from pathlib import Path
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, ContextTypes, filters
from shared.config import LOG_FORMAT, LOG_LEVEL

# Set up logging
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class KnowledgeBase:
    def __init__(self, knowledge_dir="knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.knowledge_files = {}
        self.load_knowledge_files()
    
    def load_knowledge_files(self):
        """Load all knowledge files from the knowledge directory."""
        if not self.knowledge_dir.exists():
            logger.warning(f"Knowledge directory {self.knowledge_dir} does not exist")
            return
        
        for file_path in self.knowledge_dir.glob("*.txt"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.knowledge_files[file_path.stem] = content
                    logger.info(f"Loaded knowledge file: {file_path.name}")
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}")
    
    def search_knowledge(self, query, max_results=3):
        """Search knowledge files for relevant information."""
        query_lower = query.lower()
        results = []
        
        for filename, content in self.knowledge_files.items():
            # Simple keyword matching
            lines = content.split('\n')
            relevant_lines = []
            
            for line in lines:
                line_lower = line.lower()
                # Check if any word in the query appears in the line
                query_words = query_lower.split()
                if any(word in line_lower for word in query_words if len(word) > 2):
                    relevant_lines.append(line.strip())
            
            if relevant_lines:
                results.append({
                    'file': filename,
                    'content': '\n'.join(relevant_lines[:5])  # Limit lines per file
                })
        
        # Sort by relevance (simple scoring)
        results.sort(key=lambda x: len(x['content']), reverse=True)
        return results[:max_results]
    
    def get_knowledge_context(self, query):
        """Get relevant knowledge context for a query."""
        results = self.search_knowledge(query)
        if not results:
            return ""
        
        context = "Relevant company knowledge:\n\n"
        for result in results:
            context += f"From {result['file']}:\n{result['content']}\n\n"
        
        return context

# Initialize knowledge base
knowledge_base = KnowledgeBase()

async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle knowledge search command."""
    if not context.args:
        await update.message.reply_text(
            "🔍 Knowledge Search\n\n"
            "Use: /knowledge <your question>\n\n"
            "Example: /knowledge vacation policy"
        )
        return
    
    query = ' '.join(context.args)
    await search_knowledge(update, query)

async def search_knowledge(update: Update, query: str):
    """Search knowledge base and provide answer."""
    try:
        # Search knowledge files
        results = knowledge_base.search_knowledge(query)
        
        if not results:
            await update.message.reply_text(
                "❌ I couldn't find specific information about that in our knowledge base.\n\n"
                "Try asking about:\n"
                "• Company policies\n"
                "• Product information\n"
                "• FAQ topics"
            )
            return
        
        # Format response
        response = f"🔍 Knowledge Search Results for: '{query}'\n\n"
        
        for i, result in enumerate(results, 1):
            response += f"📄 {result['file'].replace('_', ' ').title()}:\n"
            response += f"{result['content']}\n\n"
        
        # Limit message length
        if len(response) > 4000:
            response = response[:3997] + "..."
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Knowledge search error: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error while searching the knowledge base.")

async def reload_knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reload knowledge files (admin command)."""
    try:
        knowledge_base.load_knowledge_files()
        file_count = len(knowledge_base.knowledge_files)
        await update.message.reply_text(
            f"✅ Knowledge base reloaded successfully!\n"
            f"Loaded {file_count} knowledge files."
        )
    except Exception as e:
        logger.error(f"Knowledge reload error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error reloading knowledge base.")

def get_knowledge_handlers():
    """Return knowledge-related command handlers."""
    return [
        CommandHandler("knowledge", knowledge_command),
        CommandHandler("reload_knowledge", reload_knowledge_command),
    ]

def get_knowledge_context_for_chat(query):
    """Get knowledge context for integration with chat module."""
    return knowledge_base.get_knowledge_context(query) 