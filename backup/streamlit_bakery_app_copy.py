#!/usr/bin/env python3
"""
Streamlit Bakery Ecommerce Application
Integrates with MCP server for product data and recommendations
"""

import streamlit as st
import json
import requests
from typing import List, Dict, Any
import asyncio
import subprocess
import os
from dataclasses import dataclass
from datetime import datetime

# Mock data structure for demonstration (in real app, this would come from MCP server)
@dataclass
class BakeryItem:
    id: int
    name: str
    description: str
    price: float
    category: str
    ingredients: List[str]
    dietary_info: List[str]
    rating: float
    stock_quantity: int
    image_url: str

# Sample bakery data (this would normally come from the MCP server)
BAKERY_ITEMS = [
    BakeryItem(
        id=1,
        name="Classic Chocolate Chip Cookies",
        description="Soft and chewy cookies loaded with premium chocolate chips",
        price=12.99,
        category="cookies",
        ingredients=["flour", "butter", "sugar", "chocolate chips", "eggs", "vanilla"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.8,
        stock_quantity=25,
        image_url="🍪"
    ),
    BakeryItem(
        id=2,
        name="Fresh Sourdough Bread",
        description="Artisan sourdough with crispy crust and tangy flavor",
        price=8.50,
        category="bread",
        ingredients=["flour", "water", "sourdough starter", "salt"],
        dietary_info=["vegan", "contains gluten"],
        rating=4.9,
        stock_quantity=15,
        image_url="🍞"
    ),
    BakeryItem(
        id=3,
        name="Red Velvet Cupcakes",
        description="Moist red velvet cupcakes with cream cheese frosting",
        price=18.99,
        category="cupcakes",
        ingredients=["flour", "cocoa", "buttermilk", "cream cheese", "butter", "sugar"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.7,
        stock_quantity=20,
        image_url="🧁"
    ),
    BakeryItem(
        id=4,
        name="Blueberry Muffins",
        description="Fluffy muffins bursting with fresh blueberries",
        price=15.99,
        category="muffins",
        ingredients=["flour", "blueberries", "sugar", "eggs", "milk", "baking powder"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.6,
        stock_quantity=18,
        image_url="🧁"
    ),
    BakeryItem(
        id=5,
        name="Gluten-Free Almond Croissants",
        description="Buttery, flaky croissants filled with almond cream",
        price=22.99,
        category="pastries",
        ingredients=["almond flour", "butter", "eggs", "almond cream", "sugar"],
        dietary_info=["gluten-free", "contains dairy", "contains nuts"],
        rating=4.5,
        stock_quantity=12,
        image_url="🥐"
    ),
    BakeryItem(
        id=6,
        name="Classic Cheesecake",
        description="Rich and creamy New York style cheesecake",
        price=28.99,
        category="cakes",
        ingredients=["cream cheese", "eggs", "sugar", "graham crackers", "butter"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.9,
        stock_quantity=8,
        image_url="🍰"
    ),
    BakeryItem(
        id=7,
        name="Vegan Banana Bread",
        description="Moist banana bread made with plant-based ingredients",
        price=14.50,
        category="bread",
        ingredients=["flour", "bananas", "coconut oil", "almond milk", "sugar"],
        dietary_info=["vegan", "contains gluten"],
        rating=4.4,
        stock_quantity=14,
        image_url="🍞"
    ),
    BakeryItem(
        id=8,
        name="French Macarons Assortment",
        description="Delicate macarons in vanilla, chocolate, and raspberry flavors",
        price=24.99,
        category="cookies",
        ingredients=["almond flour", "sugar", "egg whites", "food coloring", "ganache"],
        dietary_info=["gluten-free", "contains nuts"],
        rating=4.8,
        stock_quantity=16,
        image_url="🍪"
    ),
    BakeryItem(
        id=9,
        name="Cinnamon Sugar Donuts",
        description="Fresh fried donuts coated in cinnamon sugar",
        price=16.99,
        category="donuts",
        ingredients=["flour", "sugar", "eggs", "milk", "cinnamon", "oil"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.7,
        stock_quantity=22,
        image_url="🍩"
    ),
    BakeryItem(
        id=10,
        name="Lemon Tart",
        description="Tangy lemon curd in a buttery pastry shell",
        price=19.99,
        category="tarts",
        ingredients=["flour", "butter", "lemons", "eggs", "sugar"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.6,
        stock_quantity=10,
        image_url="🥧"
    ),
    BakeryItem(
        id=11,
        name="Chocolate Brownies",
        description="Fudgy brownies with rich chocolate flavor",
        price=13.99,
        category="brownies",
        ingredients=["chocolate", "butter", "sugar", "eggs", "flour"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.8,
        stock_quantity=30,
        image_url="🍫"
    ),
    BakeryItem(
        id=12,
        name="Apple Pie",
        description="Traditional apple pie with flaky crust and cinnamon spice",
        price=26.99,
        category="pies",
        ingredients=["apples", "flour", "butter", "sugar", "cinnamon", "nutmeg"],
        dietary_info=["contains gluten", "contains dairy"],
        rating=4.9,
        stock_quantity=6,
        image_url="🥧"
    )
]

class BakeryRecommendationEngine:
    """Simple recommendation engine for the demo"""
    
    @staticmethod
    def get_popular_items(items: List[BakeryItem], limit: int = 5) -> List[BakeryItem]:
        return sorted(items, key=lambda x: x.rating, reverse=True)[:limit]
    
    @staticmethod
    def get_recommendations_by_preferences(items: List[BakeryItem], preferences: Dict[str, Any]) -> List[BakeryItem]:
        filtered_items = items
        
        # Filter by dietary restrictions
        if preferences.get('dietary_restrictions'):
            for restriction in preferences['dietary_restrictions']:
                filtered_items = [
                    item for item in filtered_items 
                    if restriction.lower() in [d.lower() for d in item.dietary_info]
                ]
        
        # Filter by category
        if preferences.get('category') and preferences['category'] != 'All':
            filtered_items = [
                item for item in filtered_items 
                if item.category.lower() == preferences['category'].lower()
            ]
        
        # Filter by price range
        if preferences.get('max_price'):
            filtered_items = [
                item for item in filtered_items 
                if item.price <= preferences['max_price']
            ]
        
        return sorted(filtered_items, key=lambda x: x.rating, reverse=True)[:5]
    
    @staticmethod
    def search_items(items: List[BakeryItem], query: str) -> List[BakeryItem]:
        query = query.lower()
        return [
            item for item in items 
            if query in item.name.lower() or query in item.description.lower()
        ]

# Initialize session state
if 'cart' not in st.session_state:
    st.session_state.cart = []

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def add_to_cart(item: BakeryItem):
    """Add item to cart"""
    st.session_state.cart.append(item)
    st.success(f"Added {item.name} to cart!")

def display_product_card(item: BakeryItem):
    """Display a product card"""
    with st.container():
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col1:
            st.markdown(f"<div style='font-size: 60px; text-align: center;'>{item.image_url}</div>", 
                       unsafe_allow_html=True)
        
        with col2:
            st.subheader(item.name)
            st.write(item.description)
            st.write(f"**Category:** {item.category.title()}")
            st.write(f"**Price:** ${item.price:.2f}")
            st.write(f"**Rating:** {'⭐' * int(item.rating)} ({item.rating}/5)")
            st.write(f"**Stock:** {item.stock_quantity} available")
            
            # Dietary info
            if item.dietary_info:
                dietary_badges = " ".join([f"<span style='background-color: #f0f0f0; padding: 2px 6px; border-radius: 10px; font-size: 12px; margin: 2px;'>{info}</span>" 
                                         for info in item.dietary_info])
                st.markdown(f"**Dietary Info:** {dietary_badges}", unsafe_allow_html=True)
        
        with col3:
            if st.button(f"Add to Cart", key=f"add_{item.id}"):
                add_to_cart(item)

def get_chatbot_response(user_input: str) -> str:
    """Generate chatbot response based on user input"""
    user_input_lower = user_input.lower()
    
    # Simple keyword-based responses
    if any(word in user_input_lower for word in ['recommend', 'suggestion', 'what should', 'help me choose']):
        # Extract preferences from user input
        preferences = {}
        
        # Check for dietary restrictions
        if 'vegan' in user_input_lower:
            preferences['dietary_restrictions'] = ['vegan']
        elif 'gluten' in user_input_lower or 'gluten-free' in user_input_lower:
            preferences['dietary_restrictions'] = ['gluten-free']
        
        # Check for categories
        categories = ['cookies', 'bread', 'cakes', 'muffins', 'pastries', 'donuts', 'tarts', 'brownies', 'pies']
        for category in categories:
            if category in user_input_lower:
                preferences['category'] = category
                break
        
        # Check for price mentions
        if 'cheap' in user_input_lower or 'budget' in user_input_lower or 'under 15' in user_input_lower:
            preferences['max_price'] = 15.0
        elif 'expensive' in user_input_lower or 'premium' in user_input_lower:
            preferences['max_price'] = 50.0
        
        # Get recommendations
        recommendations = BakeryRecommendationEngine.get_recommendations_by_preferences(BAKERY_ITEMS, preferences)
        
        if recommendations:
            response = "Based on your preferences, I recommend:\n\n"
            for i, item in enumerate(recommendations[:3], 1):
                response += f"{i}. **{item.name}** - ${item.price:.2f}\n   {item.description}\n   Rating: {'⭐' * int(item.rating)} ({item.rating}/5)\n\n"
            return response
        else:
            return "I couldn't find any items matching your specific preferences, but let me show you our most popular items!"
    
    elif any(word in user_input_lower for word in ['popular', 'bestseller', 'top rated', 'best']):
        popular_items = BakeryRecommendationEngine.get_popular_items(BAKERY_ITEMS, 3)
        response = "Here are our most popular items:\n\n"
        for i, item in enumerate(popular_items, 1):
            response += f"{i}. **{item.name}** - ${item.price:.2f}\n   Rating: {'⭐' * int(item.rating)} ({item.rating}/5)\n\n"
        return response
    
    elif any(word in user_input_lower for word in ['search', 'find', 'looking for']):
        # Extract search terms
        search_terms = user_input_lower.replace('search', '').replace('find', '').replace('looking for', '').strip()
        if search_terms:
            search_results = BakeryRecommendationEngine.search_items(BAKERY_ITEMS, search_terms)
            if search_results:
                response = f"I found these items matching '{search_terms}':\n\n"
                for i, item in enumerate(search_results[:3], 1):
                    response += f"{i}. **{item.name}** - ${item.price:.2f}\n   {item.description}\n\n"
                return response
            else:
                return f"Sorry, I couldn't find any items matching '{search_terms}'. Try browsing our categories!"
        else:
            return "What would you like me to search for? Try asking for specific items or browse our categories!"
    
    elif 'hello' in user_input_lower or 'hi' in user_input_lower:
        return "Hello! Welcome to our bakery! 🍰 I'm here to help you find the perfect baked goods. You can ask me for recommendations, search for specific items, or ask about our popular products. What can I help you with today?"
    
    elif 'price' in user_input_lower or 'cost' in user_input_lower:
        return "Our prices range from $8.50 for our sourdough bread to $28.99 for our classic cheesecake. Most items are between $12-$25. Would you like recommendations within a specific price range?"
    
    elif any(word in user_input_lower for word in ['vegan', 'vegetarian']):
        vegan_items = [item for item in BAKERY_ITEMS if 'vegan' in [d.lower() for d in item.dietary_info]]
        if vegan_items:
            response = "Here are our vegan options:\n\n"
            for i, item in enumerate(vegan_items, 1):
                response += f"{i}. **{item.name}** - ${item.price:.2f}\n   {item.description}\n\n"
            return response
        else:
            return "We have limited vegan options, but I recommend our Vegan Banana Bread!"
    
    elif 'gluten' in user_input_lower:
        gf_items = [item for item in BAKERY_ITEMS if 'gluten-free' in [d.lower() for d in item.dietary_info]]
        if gf_items:
            response = "Here are our gluten-free options:\n\n"
            for i, item in enumerate(gf_items, 1):
                response += f"{i}. **{item.name}** - ${item.price:.2f}\n   {item.description}\n\n"
            return response
        else:
            return "We have some gluten-free options! Check out our Gluten-Free Almond Croissants and French Macarons."
    
    else:
        return "I'm here to help you find the perfect baked goods! You can ask me for:\n- Recommendations based on your preferences\n- Our most popular items\n- Items within a specific price range\n- Vegan or gluten-free options\n- Or search for specific items\n\nWhat would you like to know?"

def main():
    """Main Streamlit app"""
    st.set_page_config(
        page_title="Sweet Delights Bakery",
        page_icon="🍰",
        layout="wide"
    )
    
    # Header
    st.title("🍰 Sweet Delights Bakery")
    st.markdown("*Freshly baked goods made with love*")
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("Choose a page", ["Browse Products", "Chat Assistant", "Shopping Cart"])
    
    if page == "Browse Products":
        st.header("Our Products")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            category_filter = st.selectbox(
                "Filter by Category",
                ["All"] + list(set(item.category.title() for item in BAKERY_ITEMS))
            )
        
        with col2:
            price_filter = st.slider("Max Price", 0, 30, 30)
        
        with col3:
            dietary_filter = st.multiselect(
                "Dietary Restrictions",
                ["vegan", "gluten-free", "contains nuts", "contains dairy"]
            )
        
        # Filter products
        filtered_items = BAKERY_ITEMS
        
        if category_filter != "All":
            filtered_items = [item for item in filtered_items if item.category.title() == category_filter]
        
        filtered_items = [item for item in filtered_items if item.price <= price_filter]
        
        if dietary_filter:
            for restriction in dietary_filter:
                filtered_items = [
                    item for item in filtered_items 
                    if restriction.lower() in [d.lower() for d in item.dietary_info]
                ]
        
        # Display products
        if filtered_items:
            for item in filtered_items:
                display_product_card(item)
                st.divider()
        else:
            st.warning("No products match your filters. Try adjusting your criteria.")
    
    elif page == "Chat Assistant":
        st.header("🤖 Bakery Assistant")
        st.markdown("Ask me for recommendations, search for products, or get help choosing the perfect treats!")
        
        # Chat interface
        chat_container = st.container()
        
        # Display chat history
        for message in st.session_state.chat_history:
            if message["role"] == "user":
                st.markdown(f"**You:** {message['content']}")
            else:
                st.markdown(f"**Assistant:** {message['content']}")
        
        # Chat input
        user_input = st.chat_input("Ask me anything about our bakery products...")
        
        if user_input:
            # Add user message to history
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            
            # Get bot response
            bot_response = get_chatbot_response(user_input)
            
            # Add bot response to history
            st.session_state.chat_history.append({"role": "assistant", "content": bot_response})
            
            # Rerun to display new messages
            st.rerun()
        
        # Sample questions
        st.subheader("Try asking:")
        sample_questions = [
            "What do you recommend for someone who loves chocolate?",
            "Show me your most popular items",
            "I need something vegan",
            "What's good for under $15?",
            "Do you have any gluten-free options?"
        ]
        
        for question in sample_questions:
            if st.button(question, key=f"sample_{question}"):
                st.session_state.chat_history.append({"role": "user", "content": question})
                bot_response = get_chatbot_response(question)
                st.session_state.chat_history.append({"role": "assistant", "content": bot_response})
                st.rerun()
    
    elif page == "Shopping Cart":
        st.header("🛒 Shopping Cart")
        
        if st.session_state.cart:
            total = 0
            for i, item in enumerate(st.session_state.cart):
                col1, col2, col3, col4 = st.columns([1, 3, 1, 1])
                
                with col1:
                    st.markdown(f"<div style='font-size: 40px;'>{item.image_url}</div>", unsafe_allow_html=True)
                
                with col2:
                    st.write(f"**{item.name}**")
                    st.write(item.description[:50] + "...")
                
                with col3:
                    st.write(f"${item.price:.2f}")
                
                with col4:
                    if st.button("Remove", key=f"remove_{i}"):
                        st.session_state.cart.pop(i)
                        st.rerun()
                
                total += item.price
                st.divider()
            
            st.subheader(f"Total: ${total:.2f}")
            
            if st.button("Proceed to Checkout", type="primary"):
                st.success("Thank you for your order! This is a demo, so no actual payment will be processed.")
                st.balloons()
                st.session_state.cart = []
        else:
            st.info("Your cart is empty. Browse our products to add items!")
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Sweet Delights Bakery**")
    st.sidebar.markdown("📍 123 Baker Street")
    st.sidebar.markdown("📞 (555) 123-CAKE")
    st.sidebar.markdown("🕒 Open 7am - 7pm daily")

if __name__ == "__main__":
    main()