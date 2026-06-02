# Huffman File Compression Web Application

A cloud-native file compression and decompression platform built with Flask and C++, utilizing the Huffman Coding algorithm to reduce file size while preserving data integrity.

The project combines a Python Flask web application with a native C++ compression engine, providing a modern browser-based interface for compressing and restoring files across multiple operating systems and deployment environments.

---

# Project Overview

This application allows users to upload files through a web interface, compress them using a Huffman Coding implementation written in C++, and download the resulting compressed output.

The system also supports decompression, restoring files back to their original form while preserving the original file extension and content.

Unlike traditional desktop-only implementations, this project was designed to run both locally and in cloud environments such as Render.

---

# Key Features

### Compression

* Huffman Coding compression engine written in C++
* Supports single-file and multi-file compression
* Supports text and binary files
* Automatic compression statistics generation
* Compression ratio calculation
* Storage savings calculation
* Entropy analysis

### Decompression

* Restores original files from Huffman-compressed `.bin` files
* Preserves original file extension
* Supports batch decompression
* Integrity validation during decoding

### Analysis Features

* Shannon Entropy estimation
* Compression efficiency calculations
* Top-frequency symbol reporting
* Huffman code length analysis
* Office document deep-scan analysis

### Office File Analysis

Special handling for:

* `.docx`
* `.pptx`
* `.xlsx`

The application can inspect Office ZIP containers and analyze internal XML content to provide realistic compression expectations.

### Cloud-Native Architecture

* Stateless processing
* Temporary session directories
* Automatic cleanup
* No persistent file storage
* Render deployment support
* Linux deployment support
* Windows local development support

### User Interface

* Responsive design
* Mobile-friendly layout
* Multi-file upload support
* Drag-and-drop uploads
* Dark theme interface
* Real-time compression results
* Download-ready output packages

---

# Technology Stack

## Backend

* Python 3
* Flask
* Werkzeug

## Compression Engine

* C++
* Huffman Coding Algorithm
* Binary file processing

## Frontend

* HTML5
* CSS3
* JavaScript

## Deployment

* Gunicorn
* Render
* Linux
* Windows

---

# System Architecture

Browser

↓

Flask Routes

↓

Temporary Session Directory

↓

Uploaded File Storage

↓

C++ Huffman Executable

↓

Compressed / Decompressed Output

↓

ZIP Packaging

↓

Base64 Encoding

↓

JSON Response

↓

Browser Download

---

# Supported File Types

The application accepts virtually any file type because processing occurs at the byte level.

Examples include:

* TXT
* DOC
* DOCX
* PPT
* PPTX
* XLSX
* PDF
* CSV
* JSON
* XML
* LOG
* Images
* Binary Files

Compression effectiveness varies depending on the amount of redundancy present in the file.

Files that are already compressed may show minimal gains.

Examples:

* ZIP
* RAR
* JPG
* PNG
* MP3
* MP4

---

# Project Structure

```text
project/
│
├── main.py
├── requirements.txt
├── render.yaml
│
├── compressor/
│   ├── huffcompress.cpp
│   ├── huffdecompress.cpp
│   ├── huffcompress.exe
│   └── huffdecompress.exe
│
├── templates/
│   ├── index.html
│   ├── compress.html
│   ├── decompress.html
│   └── about.html
│
├── static/
│   ├── css/
│   ├── js/
│   └── assets/
│
├── uploads/
├── downloads/
├── temp/
└── tests/
```

---

# Installation

## Clone Repository

```bash
git clone <repository-url>
cd project
```

## Create Virtual Environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Build Compression Binaries

## Windows

```bash
cd compressor

g++ -O2 -o huffcompress.exe huffcompress.cpp

g++ -O2 -o huffdecompress.exe huffdecompress.cpp
```

## Linux

```bash
cd compressor

g++ -O2 -o huffcompress huffcompress.cpp

g++ -O2 -o huffdecompress huffdecompress.cpp
```

---

# Run Locally

```bash
python main.py
```

Application:

```text
http://localhost:5000
```

---

# API Routes

| Route       | Method    | Description            |
| ----------- | --------- | ---------------------- |
| /           | GET       | Home Page              |
| /compress   | GET, POST | File Compression       |
| /decompress | GET, POST | File Decompression     |
| /about      | GET       | About Page             |
| /debug      | GET       | Deployment Diagnostics |

---

# Security Features

* Secure filename sanitization
* Temporary session isolation
* Automatic file cleanup
* Upload size limits
* Binary validation
* Subprocess error handling
* Timeout protection
* Cross-platform path handling

---

# Known Limitations

* Huffman Coding is less effective on already compressed files.
* Large files require additional memory during ZIP packaging and Base64 encoding.
* Files are processed sequentially.
* Compression performance depends on hardware resources.

---

# Future Improvements

* Parallel processing
* Streaming downloads
* Adaptive Huffman Coding
* Compression benchmarking
* Docker support
* Automated testing pipeline
* User authentication
* Compression history dashboard

---

# Development Team

### Arman Christian Malgapo

Lead Developer & Backend Systems Programmer

Responsible for system architecture, Flask integration, C++ integration, deployment configuration, backend implementation, debugging, and feature development.

### Nikko Madueño

Quality Assurance & Testing Specialist

Responsible for validation, testing procedures, and usability verification.

### Paul Henrick Maquiniana

Project Coordinator & Development Manager

Responsible for project organization, planning, coordination, and workflow management.

### Theo Masato Nakajima

Technical Documentation & Research Specialist

Responsible for documentation, technical writing, research, and project records.

---

# Academic Purpose

This project was developed as an educational implementation of Huffman Coding to demonstrate lossless data compression, file handling, web application development, cross-language integration between Python and C++, and cloud deployment practices.

---

# Current Version

Version: 2.0

Status: Stable

Platform Support:

* Windows
* Linux
* Render Cloud Deployment

Compression Engine:

* Huffman Coding (Lossless Compression)

Last Updated: 2026
