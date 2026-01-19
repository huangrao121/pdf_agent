
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi.errors import RateLimitExceeded

from pdf_ai_agent.api.utils import generate_request_id

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from pdf_ai_agent.config.database.init_database import get_database_config, init_database, close_engine

    config = get_database_config()
    await init_database(config)
    yield
    await close_engine()


# 入口函数
def create_app():
    load_dotenv()
    app = FastAPI(title="PDF_Agent", lifespan=lifespan)
    
    # Import and register routers
    from pdf_ai_agent.api.v1.auth.router import router as auth_router
    from pdf_ai_agent.api.rate_limit import limiter
    
    # Add rate limiter to app state
    app.state.limiter = limiter
    
    # Register exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation errors with consistent error format."""
        request_id = generate_request_id()
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            errors.append({
                "field": field,
                "reason": error["msg"]
            })
        
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "Input validation failed.",
                    "request_id": request_id,
                },
                "errors": errors
            }
        )
    
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """Handle rate limit exceeded errors."""
        request_id = generate_request_id()
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please try again later.",
                    "request_id": request_id,
                }
            },
            headers={"Retry-After": "60"}
        )
    
    # Register routers
    app.include_router(auth_router, prefix="/api")
    
    @app.get("/health", tags=["Health Check"])
    async def health_check():
        return {"status": "ok"}
    
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:create_app", host="0.0.0.0", port=8000, reload=True)
