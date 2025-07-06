#!/usr/bin/env python3
"""
Model Context Protocol Server for Bakery Ecommerce
Provides product data and recommendations for bakery items
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

# MCP imports (you'll need to install: pip install mcp)
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    CallToolRequest,
    CallToolResult,
    GetResourceRequest,
    GetResourceResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BakeryItem:
    id: int
    name: str
    description: str
    price: float
    category: str
    ingredients: List[str]
    dietary_info: List[str]  # e.g., ["gluten-free", "vegan", "nut-free"]
    rating: float
    stock_quantity: int
    image_url: str

class BakeryDatabase:
    """Mock database for bakery items"""
    
    def __init__(self):
        self.items = [
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
                image_url="https://example.com/chocolate-chip-cookies.jpg"
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
                image_url="https://example.com/sourdough.jpg"
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
                image_url="https://example.com/red-velvet-cupcakes.jpg"
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
                image_url="https://example.com/blueberry-muffins.jpg"
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
                image_url="https://example.com/almond-croissants.jpg"
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
                image_url="https://example.com/cheesecake.jpg"
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
                image_url="https://example.com/banana-bread.jpg"
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
                image_url="https://example.com/macarons.jpg"
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
                image_url="https://example.com/cinnamon-donuts.jpg"
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
                image_url="https://example.com/lemon-tart.jpg"
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
                image_url="https://example.com/brownies.jpg"
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
                image_url="https://example.com/apple-pie.jpg"
            )
        ]
    
    def get_all_items(self) -> List[BakeryItem]:
        return self.items
    
    def get_item_by_id(self, item_id: int) -> Optional[BakeryItem]:
        return next((item for item in self.items if item.id == item_id), None)
    
    def get_items_by_category(self, category: str) -> List[BakeryItem]:
        return [item for item in self.items if item.category.lower() == category.lower()]
    
    def get_items_by_dietary_restriction(self, restriction: str) -> List[BakeryItem]:
        return [item for item in self.items if restriction.lower() in [d.lower() for d in item.dietary_info]]
    
    def search_items(self, query: str) -> List[BakeryItem]:
        query = query.lower()
        return [
            item for item in self.items 
            if query in item.name.lower() or query in item.description.lower()
        ]

class BakeryRecommendationEngine:
    """Recommendation engine for bakery items"""
    
    def __init__(self, database: BakeryDatabase):
        self.db = database
    
    def get_popular_items(self, limit: int = 5) -> List[BakeryItem]:
        """Get most popular items based on rating"""
        items = self.db.get_all_items()
        return sorted(items, key=lambda x: x.rating, reverse=True)[:limit]
    
    def get_recommendations_by_preference(self, preferences: Dict[str, Any]) -> List[BakeryItem]:
        """Get recommendations based on user preferences"""
        items = self.db.get_all_items()
        filtered_items = items
        
        # Filter by dietary restrictions
        if 'dietary_restrictions' in preferences:
            for restriction in preferences['dietary_restrictions']:
                filtered_items = [
                    item for item in filtered_items 
                    if restriction.lower() in [d.lower() for d in item.dietary_info]
                ]
        
        # Filter by category preference
        if 'category' in preferences:
            filtered_items = [
                item for item in filtered_items 
                if item.category.lower() == preferences['category'].lower()
            ]
        
        # Filter by price range
        if 'max_price' in preferences:
            filtered_items = [
                item for item in filtered_items 
                if item.price <= preferences['max_price']
            ]
        
        # Sort by rating and return top results
        return sorted(filtered_items, key=lambda x: x.rating, reverse=True)[:5]

# Initialize database and recommendation engine
db = BakeryDatabase()
recommendation_engine = BakeryRecommendationEngine(db)

# Create MCP server
server = Server("bakery-ecommerce")

@server.list_resources()
async def handle_list_resources() -> ListResourcesResult:
    """List available resources"""
    return ListResourcesResult(
        resources=[
            Resource(
                uri="bakery://products/all",
                name="All Bakery Products",
                description="Complete list of all bakery items",
                mimeType="application/json",
            ),
            Resource(
                uri="bakery://products/categories",
                name="Product Categories",
                description="List of all product categories",
                mimeType="application/json",
            )
        ]
    )

@server.get_resource()
async def handle_get_resource(request: GetResourceRequest) -> GetResourceResult:
    """Get resource content"""
    if request.uri == "bakery://products/all":
        items = db.get_all_items()
        items_data = [asdict(item) for item in items]
        return GetResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(items_data, indent=2)
                )
            ]
        )
    elif request.uri == "bakery://products/categories":
        items = db.get_all_items()
        categories = list(set(item.category for item in items))
        return GetResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(categories, indent=2)
                )
            ]
        )
    else:
        raise ValueError(f"Unknown resource: {request.uri}")

@server.list_tools()
async def handle_list_tools() -> ListToolsResult:
    """List available tools"""
    return ListToolsResult(
        tools=[
            Tool(
                name="get_product_recommendations",
                description="Get product recommendations based on user preferences",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "preferences": {
                            "type": "object",
                            "properties": {
                                "dietary_restrictions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Dietary restrictions (e.g., vegan, gluten-free)"
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Preferred product category"
                                },
                                "max_price": {
                                    "type": "number",
                                    "description": "Maximum price range"
                                }
                            }
                        }
                    }
                }
            ),
            Tool(
                name="search_products",
                description="Search for products by name or description",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_popular_products",
                description="Get most popular products based on ratings",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of products to return",
                            "default": 5
                        }
                    }
                }
            ),
            Tool(
                name="get_product_details",
                description="Get detailed information about a specific product",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "integer",
                            "description": "Product ID"
                        }
                    },
                    "required": ["product_id"]
                }
            )
        ]
    )

@server.call_tool()
async def handle_call_tool(request: CallToolRequest) -> CallToolResult:
    """Handle tool calls"""
    
    if request.name == "get_product_recommendations":
        preferences = request.arguments.get("preferences", {})
        recommendations = recommendation_engine.get_recommendations_by_preference(preferences)
        recommendations_data = [asdict(item) for item in recommendations]
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(recommendations_data, indent=2)
                )
            ]
        )
    
    elif request.name == "search_products":
        query = request.arguments["query"]
        results = db.search_items(query)
        results_data = [asdict(item) for item in results]
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(results_data, indent=2)
                )
            ]
        )
    
    elif request.name == "get_popular_products":
        limit = request.arguments.get("limit", 5)
        popular_items = recommendation_engine.get_popular_items(limit)
        popular_data = [asdict(item) for item in popular_items]
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(popular_data, indent=2)
                )
            ]
        )
    
    elif request.name == "get_product_details":
        product_id = request.arguments["product_id"]
        item = db.get_item_by_id(product_id)
        
        if item:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(asdict(item), indent=2)
                    )
                ]
            )
        else:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "Product not found"})
                    )
                ]
            )
    
    else:
        raise ValueError(f"Unknown tool: {request.name}")

async def main():
    """Main server function"""
    logger.info("Starting Bakery MCP Server...")
    
    # Run the server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="bakery-ecommerce",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                )
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())