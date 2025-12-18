# Feed Service

Microservice responsible for post management, feed generation, and social feed-related operations.

## 📋 Overview

The Feed Service handles all post and feed-related functionality including:
- Post creation and management
- Feed generation with pagination
- Interest-based post discovery
- Post interest management
- Like/unlike functionality

## 🏗️ Architecture

```
API Gateway → Composite Service → Feed Service → Feed Database (Cloud SQL)
```

- **Port**: 8003
- **Database**: MySQL (Cloud SQL or local)
- **Authentication**: Trusts `x-firebase-uid` header from API Gateway
- **Deployment**: Can run on Cloud Run or Compute Engine VM

## 🚀 Setup

### Prerequisites

- Python 3.9+
- MySQL 8.0+
- Firebase service account key

### Installation

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up database**
   ```bash
   mysql -u root -p feed_db < ../DB-Service/initFeed.sql
   ```

3. **Configure environment variables**
   Create a `.env` file:
   ```env
   DB_HOST=127.0.0.1
   DB_USER=root
   DB_PASS=your_password
   DB_NAME=feed_db
   FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json
   ```

4. **Add Firebase service account key**
   - Download from Firebase Console
   - Place as `serviceAccountKey.json` in service directory

5. **Run the service**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8003
   ```

## 🔧 Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|---------|
| `DB_HOST` | Database host address | `127.0.0.1` | Yes |
| `DB_USER` | Database username | `root` | Yes |
| `DB_PASS` | Database password | - | Yes |
| `DB_NAME` | Database name | `feed_db` | Yes |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to Firebase service account JSON | `./serviceAccountKey.json` | No |

## 📡 API Endpoints

### Post Management

#### `GET /posts`
Get all posts with pagination and filtering

**Query Parameters:**
- `skip`: Number of posts to skip (default: 0)
- `limit`: Number of posts to return (default: 10, max: 100)
- `interest_id`: Filter by interest ID
- `created_by`: Filter by creator user ID
- `search`: Search in title and body

**Headers:**
- `x-firebase-uid`: Firebase user ID (injected by API Gateway)

**Response:**
```json
{
  "items": [
    {
      "post_id": 1,
      "title": "My First Post",
      "body": "This is my first post!",
      "created_by": 1,
      "created_at": "2024-01-01T00:00:00",
      "likes_count": 5,
      "interests": [
        {"interest_id": 1, "interest_name": "Technology"}
      ],
      "_links": {
        "self": {"href": "/posts/1"},
        "collection": {"href": "/posts"}
      }
    }
  ],
  "total": 50,
  "skip": 0,
  "limit": 10
}
```

**ETag Support**: Returns `ETag` header for caching

#### `GET /posts/{post_id}`
Get post by ID

**Response:**
```json
{
  "post_id": 1,
  "title": "My First Post",
  "body": "This is my first post!",
  "created_by": 1,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "likes_count": 5,
  "interests": [...],
  "_links": {...}
}
```

#### `POST /posts`
Create a new post

**Request Body:**
```json
{
  "title": "My First Post",
  "body": "This is my first post!",
  "interest_ids": [1, 2, 3]
}
```

**Response:**
- `201 Created` with post data

#### `PUT /posts/{post_id}`
Update a post (full update)

**Request Body:**
```json
{
  "title": "Updated Post Title",
  "body": "Updated post body",
  "interest_ids": [1, 2]
}
```

**ETag Support**: Requires `If-Match` header for optimistic locking

#### `PATCH /posts/{post_id}`
Partially update a post

**Request Body:**
```json
{
  "title": "Updated Title"
}
```

**ETag Support**: Requires `If-Match` header

#### `DELETE /posts/{post_id}`
Delete a post

**ETag Support**: Requires `If-Match` header

### Post Interests

#### `GET /posts/{post_id}/interests`
Get interests for a post

#### `POST /posts/{post_id}/interests`
Add interests to a post

**Request Body:**
```json
{
  "interest_ids": [1, 2, 3]
}
```

#### `DELETE /posts/{post_id}/interests/{interest_id}`
Remove interest from a post

### Post Likes

#### `POST /posts/{post_id}/like`
Like a post

**Response:**
```json
{
  "post_id": 1,
  "likes_count": 6,
  "liked": true
}
```

#### `DELETE /posts/{post_id}/like`
Unlike a post

**Response:**
```json
{
  "post_id": 1,
  "likes_count": 5,
  "liked": false
}
```

### Feed Endpoints

#### `GET /posts/feed`
Get personalized feed for current user

**Query Parameters:**
- `skip`: Number of posts to skip (default: 0)
- `limit`: Number of posts to return (default: 10, max: 100)

**Response:**
Returns posts from users the current user follows, ordered by creation date.

## 🔐 Authentication

This service **does not** perform Firebase authentication directly. It trusts the `x-firebase-uid` header injected by the API Gateway middleware.

## 🗄️ Database Schema

### Posts Table
- `post_id` (INT, PRIMARY KEY, AUTO_INCREMENT)
- `title` (VARCHAR)
- `body` (TEXT)
- `created_by` (INT, FOREIGN KEY to Users)
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

### PostInterests Table (Many-to-Many)
- `post_id` (INT, FOREIGN KEY)
- `interest_id` (INT, FOREIGN KEY)

### PostLikes Table
- `post_id` (INT, FOREIGN KEY)
- `user_id` (INT, FOREIGN KEY)
- `created_at` (TIMESTAMP)
- PRIMARY KEY (post_id, user_id)

### Interests Table
- `interest_id` (INT, PRIMARY KEY)
- `interest_name` (VARCHAR, UNIQUE)

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t feed-service .
```

### Run Container
```bash
docker run -p 8003:8003 \
  -e DB_HOST=your_db_host \
  -e DB_USER=your_db_user \
  -e DB_PASS=your_db_password \
  -e DB_NAME=feed_db \
  feed-service
```

## ☁️ GCP Deployment

### Cloud Run Deployment
The service can be deployed to Cloud Run with:
- VPC Connector for database access
- Private IP connection to Cloud SQL
- Environment variables configured via deployment script

### Compute Engine VM Deployment
The service can also run on a Compute Engine VM:
- Direct VPC connection to Cloud SQL
- Systemd service for auto-start
- No external IP required

See [../GCP_DEPLOYMENT_GUIDE.md](../GCP_DEPLOYMENT_GUIDE.md) for details.

## 🧪 Testing

### Health Check
```bash
curl http://localhost:8003/
```

### Get Posts
```bash
curl -H "x-firebase-uid: your-firebase-uid" \
     http://localhost:8003/posts
```

### Create Post
```bash
curl -X POST \
     -H "x-firebase-uid: your-firebase-uid" \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Test Post",
       "body": "Test post body",
       "interest_ids": [1]
     }' \
     http://localhost:8003/posts
```

### Like Post
```bash
curl -X POST \
     -H "x-firebase-uid: your-firebase-uid" \
     http://localhost:8003/posts/1/like
```

## 📚 API Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8003/docs`
- ReDoc: `http://localhost:8003/redoc`
- OpenAPI JSON: `http://localhost:8003/openapi.json`

## 🔍 Error Handling

The service returns standard HTTP status codes:

- `200 OK`: Successful request
- `201 Created`: Post created
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid `x-firebase-uid` header
- `404 Not Found`: Post not found
- `409 Conflict`: ETag mismatch (optimistic locking)
- `412 Precondition Failed`: ETag required but not provided
- `500 Internal Server Error`: Server error

## 🎯 Features

- **HATEOAS**: All responses include `_links` for navigation
- **ETag Support**: Optimistic locking for updates
- **Pagination**: Skip/limit for large result sets
- **Filtering**: By interest, creator, search
- **Like System**: Users can like/unlike posts
- **Interest Tags**: Posts can be tagged with interests

## 📝 Notes

- The service uses MySQL connector with dictionary cursor for JSON-like responses
- ETag is generated from post data for optimistic locking
- Like counts are calculated dynamically from PostLikes table
- All datetime fields use ISO 8601 format

## 🤝 Contributing

When adding new endpoints:
1. Add route to `routers/posts.py`
2. Use `get_firebase_uid_from_header()` helper for authentication
3. Add proper error handling and ETag support
4. Update this README with endpoint documentation
