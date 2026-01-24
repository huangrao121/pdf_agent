
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv(".env.dev")

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
    app = FastAPI(title="PDF_Agent",lifespan=lifespan)
    
    # Register routers
    from pdf_ai_agent.api.routes.auth import router as auth_router
    from pdf_ai_agent.api.routes.documents import router as documents_router
    
    app.include_router(auth_router)
    app.include_router(documents_router)
    
    @app.get("/health", tags=["Health Check"])
    async def health_check():
        return {"status": "ok"}
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:create_app", host="0.0.0.0", port=8000, reload=True)
