"""Main FastAPI application for Arth."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="Arth",
    description="An internal, agentic personal-finance system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with basic HTML response."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Arth - Personal Finance System</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://unpkg.com/htmx.org@1.9.10"></script>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 min-h-screen">
        <div class="container mx-auto px-4 py-8">
            <div class="max-w-4xl mx-auto">
                <h1 class="text-4xl font-bold text-gray-900 mb-8 text-center">
                    🏦 Arth
                </h1>
                <p class="text-xl text-gray-600 text-center mb-8">
                    Your personal finance system is running!
                </p>
                <div class="bg-white rounded-lg shadow-md p-6">
                    <h2 class="text-2xl font-semibold mb-4">System Status</h2>
                    <div class="space-y-2">
                        <div class="flex items-center">
                            <div class="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                            <span>API Server: Running</span>
                        </div>
                        <div class="flex items-center">
                            <div class="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                            <span>Database: Connected</span>
                        </div>
                        <div class="flex items-center">
                            <div class="w-3 h-3 bg-yellow-500 rounded-full mr-3"></div>
                            <span>ETL Pipeline: Not configured</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/v1/healthz")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "arth"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 