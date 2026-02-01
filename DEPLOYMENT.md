# Production Deployment Checklist

## Railway (Backend + Database)

### Environment Variables to Set in Railway:
1. **JWT_SECRET** (CRITICAL - Required)
   - Generate using: `python -c 'import secrets; print(secrets.token_urlsafe(32))'`
   - Set this in Railway dashboard under "Variables"

2. **DATABASE_URL** 
   - Automatically provided by Railway Postgres plugin
   - No action needed if using Railway's Postgres

3. **ACCESS_TOKEN_EXPIRE_MINUTES** (Optional)
   - Default: 60 minutes
   - Recommended: 60-120 for production

4. **DB_POOL_SIZE** (Optional)
   - Default: 20
   - Adjust based on Railway plan

5. **DB_MAX_OVERFLOW** (Optional)
   - Default: 10

6. **SQL_ECHO** (Optional)
   - Set to "False" for production (default)

7. **ENVIRONMENT**
   - Set to "production"

### Railway Setup Steps:
1. Create a new project in Railway
2. Add Postgres database (Railway will auto-inject DATABASE_URL)
3. Deploy backend from GitHub repository
4. Set environment variables listed above
5. Deploy and verify health endpoint: `https://your-app.railway.app/api/health`

## Vercel (Frontend)

### Environment Variables to Set in Vercel:
1. **NEXT_PUBLIC_API_URL**
   - Set to your Railway backend URL: `https://your-app.railway.app`

### Vercel Setup Steps:
1. Import project from GitHub
2. Set framework preset to "Next.js"
3. Set root directory to "frontend"
4. Add environment variable for backend URL
5. Deploy

## Security Checklist

✅ **JWT_SECRET is set and secure** (not "dev-secret")
✅ **CORS origins are configured** in `backend/main.py`:
   - Update `allow_origins` list with your actual Vercel domain
   - Remove localhost origins for production if not needed

✅ **HTTPS is enabled** (Railway and Vercel provide this by default)
✅ **Database connection uses SSL** (Railway Postgres includes this)
✅ **Token expiration is reasonable** (60-120 minutes recommended)
✅ **Password hashing uses bcrypt with cost factor 12**
✅ **Proper logging configured** (info level for production)

## Post-Deployment Verification

1. Test health endpoint: `curl https://your-backend.railway.app/api/health`
2. Test user registration and login
3. Verify JWT tokens are working
4. Check logs in Railway dashboard for any errors
5. Test CORS from Vercel frontend
6. Monitor database connection pool usage

## Common Issues and Solutions

### Issue: "JWT_SECRET environment variable is not set"
**Solution**: Set JWT_SECRET in Railway environment variables

### Issue: CORS errors from frontend
**Solution**: Add your Vercel domain to `allow_origins` in `backend/main.py`:
```python
allow_origins=[
    "https://your-vercel-domain.vercel.app",
    "https://your-production-domain.com"
]
```

### Issue: Database connection errors
**Solution**: Verify DATABASE_URL is set and Postgres plugin is active in Railway

### Issue: "Invalid or expired token"
**Solution**: 
- Ensure JWT_SECRET is the same across all backend instances
- Check token expiration time
- Verify clock sync between client and server

## Monitoring

1. **Railway Dashboard**: Monitor CPU, memory, and request metrics
2. **Logs**: Check Railway logs for errors and warnings
3. **Database**: Monitor connection pool usage and query performance
4. **Uptime**: Set up monitoring (e.g., UptimeRobot, Better Stack)

## Rollback Plan

If issues occur after deployment:
1. Railway: Revert to previous deployment from dashboard
2. Vercel: Revert to previous deployment or redeploy from Git
3. Check environment variables haven't changed
4. Review recent commits for breaking changes
