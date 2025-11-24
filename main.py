from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import posts

app = FastAPI(
    title="Feed Service",
    description="Handles user posts and feed management",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "etag", "Location", "Content-Type"]  # Expose ETag header to frontend
)

app.include_router(posts.router)

@app.get("/")
def root():
    return {"status": "Feed Service running"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "users"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

