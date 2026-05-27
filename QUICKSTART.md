# Quick Start Guide

## For Immediate Testing (Local Development)

### Windows
```bash
# 1. Build C++ binaries
build.bat

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python main.py

# 4. Open browser
# Visit: http://localhost:5000
```

### Linux / macOS
```bash
# 1. Build C++ binaries
chmod +x build.sh
./build.sh

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python main.py

# 4. Open browser
# Visit: http://localhost:5000
```

---

## For Production Deployment (Render)

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Cloud-native refactoring for Render deployment"
git push origin main
```

### Step 2: Deploy on Render
1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click "New" → "Web Service"
3. Select your GitHub repository
4. Render will automatically detect `render.yaml`
5. Click "Deploy"

### Step 3: Monitor Deployment
- Watch the build logs
- Verify C++ binaries compile
- Confirm app starts without errors
- App will be live at: `https://your-app-name.onrender.com`

---

## How It Works (New Stateless Model)

### Compression Flow
```
User uploads file
     ↓
Server creates temporary directory
     ↓
Saves file to temp directory
     ↓
C++ compressor processes file
     ↓
Reads output file into memory
     ↓
Base64 encodes the data
     ↓
Returns JSON with encoded data
     ↓
Temporary directory auto-deleted
     ↓
Browser downloads file from encoded data
```

### Key Improvements
✅ No persistent file storage on server
✅ Zero disk accumulation
✅ Works on any OS (Windows/Linux/macOS)
✅ Scalable to multiple instances
✅ Automatic cleanup (no manual management)

---

## Testing the App

### Using the Web UI
1. Go to http://localhost:5000
2. Click "Compress Files"
3. Upload a file (TXT, PDF, etc.)
4. View results and download
5. Try decompression with the `.bin` file

### Using curl (Command Line)
```bash
# Test compression
curl -X POST http://localhost:5000/compress \
  -F "files=@myfile.txt"

# Response includes base64-encoded compressed data
```

---

## File Structure (After Refactoring)

### Directories Used
```
project/
├── main.py                  # Flask app (cloud-native)
├── requirements.txt         # Python dependencies
├── render.yaml              # Render deployment config
├── DEPLOYMENT.md            # Detailed deployment guide
├── CLOUD_REFACTORING_SUMMARY.md  # What changed
├── build.sh                 # Linux build script
├── build.bat                # Windows build script
├── .env.example             # Environment template
├── .gitignore               # Git ignore rules
│
├── compressor/
│   ├── huffcompress.cpp
│   ├── huffdecompress.cpp
│   ├── huffcompress         # (created by build.sh)
│   └── huffdecompress       # (created by build.sh)
│
├── templates/               # HTML UI (unchanged)
├── static/                  # CSS/JS assets (unchanged)
└── tests/                   # Sample files for testing
```

### No Longer Used
```
❌ uploads/        (was: uploaded files)
❌ downloads/      (was: processed files)
❌ temp/          (was: temporary workspace)
❌ downloads/jobs/ (was: job metadata)
```

---

## Configuration

### Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env`:
```
SECRET_KEY=your-secure-key-here
PYTHON_VERSION=3.11
```

### Upload Limits
- Max file size: 100MB (in `main.py`)
- Max file size: 100MB (in `main.py`)
     (All file types are accepted by the server; compression efficiency may vary.)

---

## Troubleshooting

### "Compressor binary not found"
**Solution:**
```bash
# Windows
build.bat

# Linux/macOS
./build.sh
```

### App won't start
**Check for:**
1. Python 3.8+: `python --version`
2. Dependencies: `pip install -r requirements.txt`
3. Binaries: Run build script above
4. Port available: `python main.py` uses port 5000

### Upload fails with 413 error
- File size exceeds 100MB limit
- Reduce file size or modify `MAX_CONTENT_LENGTH` in main.py

### Files not downloading
- Ensure JavaScript is enabled in browser
- Check browser console for errors (F12 → Console tab)
- Try a smaller file first

---

## What's Different from the Old Version?

| Aspect | Old | New |
|--------|-----|-----|
| File Storage | Permanent directories | Temporary (auto-cleaned) |
| Platform Support | Windows only | Windows/Linux/macOS |
| Download Method | Server file serving | Browser blob download |
| Scalability | Single instance only | Multi-instance ready |
| Deployment | Manual setup | Render auto-deploy |
| Maintenance | Manual cleanup | Zero maintenance |

---

## Next Steps

1. **Test locally** (follow Quick Start above)
2. **Read DEPLOYMENT.md** for detailed info
3. **Deploy to Render** (see Production Deployment)
4. **Monitor logs** in Render dashboard
5. **Share your app** - it's production-ready!

---

## Support Resources

- **DEPLOYMENT.md** - Full deployment guide with troubleshooting
- **CLOUD_REFACTORING_SUMMARY.md** - Technical details of changes
- **main.py** - Well-commented source code
- **Render Docs** - https://render.com/docs

---

**Ready to deploy?** Start with the Quick Start section above!
