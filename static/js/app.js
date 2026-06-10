//* ============================================================================
//* THEME TOGGLE - Dark/Light Mode
//* ============================================================================

const themeToggle = document.getElementById('theme-toggle');
const body = document.body;

function initThemeToggle() {
    if (!themeToggle) return;

    //* Load saved theme preference from localStorage
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme === 'light') {
        body.classList.add('light-mode');
        themeToggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
    } else {
        themeToggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
    }

    //! Toggle theme on click and persist preference
    themeToggle.addEventListener('click', () => {
        body.classList.toggle('light-mode');

        const isLight = body.classList.contains('light-mode');

        themeToggle.innerHTML = isLight
            ? '<i class="fa-solid fa-sun"></i>'
            : '<i class="fa-solid fa-moon"></i>';

        localStorage.setItem('theme', isLight ? 'light' : 'dark');
    });
}

//* ============================================================================
//* SIDEBAR NAVIGATION - Active Page Highlighting
//* ============================================================================

function initSidebarNav() {
    const currentPath = window.location.pathname;
    const navItems = document.querySelectorAll('.nav-item');

    navItems.forEach((item) => {
        const href = item.getAttribute('href');

        //! Highlight current page navigation item
        if (href === currentPath || (currentPath === '/' && href === '/')) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }

        //* Update active state on click
        item.addEventListener('click', () => {
            navItems.forEach((nav) => nav.classList.remove('active'));
            item.classList.add('active');
        });
    });
}

//* ============================================================================
//* FILE UPLOAD - Drag & Drop and Click to Browse
//* ============================================================================

function initUploadBoxes() {
    const uploadBoxes = document.querySelectorAll('.upload-box');

    uploadBoxes.forEach((box) => {
        const input = box.querySelector('input[type="file"]');
        if (!input) return;

        //! Click to open file browser
        box.addEventListener('click', () => input.click());

        //! Visual feedback during drag
        box.addEventListener('dragover', (e) => {
            e.preventDefault();
            box.classList.add('dragover');
        });

        box.addEventListener('dragleave', () => box.classList.remove('dragover'));

        //! Handle dropped files
        box.addEventListener('drop', (e) => {
            e.preventDefault();
            box.classList.remove('dragover');
            input.files = e.dataTransfer.files;
            updateUploadText(box, input.files);
        });

        input.addEventListener('change', () => updateUploadText(box, input.files));
    });
}

//* Update upload box display text based on selected files
function updateUploadText(box, files) {
    const text = box.querySelector('#upload-text-content');
    if (!text) return;

    if (!files || files.length === 0) {
        text.textContent = 'Drag and drop files here or click to browse';
        return;
    }

    text.textContent = files.length === 1
        ? `Selected: ${files[0].name}`
        : `${files.length} files selected`;
}

//* ============================================================================
//* RESULT RENDERING - Display compression/decompression results
//* ============================================================================

function buildResults(result) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'result-item';

    if (result.success) {
        //* Build optional metadata sections
        const savedText = result.saved_bytes !== undefined
            ? `Saved: ${formatBytes(result.saved_bytes)}`
            : '';

        //! Display top 5 most frequent bytes in file
        const metaHtml = result.top_symbols && result.top_symbols.length
            ? `<div class="result-meta">${result.top_symbols.map(symbol => `<span class="tag">Byte ${symbol.byte} • ${symbol.frequency}× • ${symbol.code_length} bits</span>`).join(' ')}</div>`
            : '';

        //! Warn if file is already highly compressed
        const entropyHtml = result.entropy_warning
            ? `<p class="result-note">⚠️ ${result.entropy_warning}</p>`
            : '';

        //! Deep scan results for Office files (docx, pptx, xlsx)
        const deepScanHtml = result.deep_scan && result.deep_scan.office_archive
            ? `<div class="result-subnote"><p><strong>Deep Scan:</strong> ${result.deep_scan.office_message}</p><p>${result.deep_scan.office_xml_files} XML text layers detected (${result.deep_scan.office_xml_ratio}% of archive).</p></div>`
            : '';

        resultDiv.innerHTML = `
            <div class="result-success">
                <p><strong>✓ ${result.filename}</strong></p>
                ${result.original_size ? `<p>Original: ${formatBytes(result.original_size)}</p>` : ''}
                ${result.compressed_size ? `<p>Compressed: ${formatBytes(result.compressed_size)}</p>` : ''}
                ${result.decompression_size ? `<p>Restored Size: ${formatBytes(result.decompressed_size)}</p>` : ''}
                ${result.compression_ratio ? `<p>Ratio: ${result.compression_ratio}%</p>` : ''}
                ${savedText ? `<p>${savedText}</p>` : ''}
                ${result.average_bits_per_symbol ? `<p>Avg bits/symbol: ${result.average_bits_per_symbol}</p>` : ''}
                ${result.efficiency_vs_8bit ? `<p>8-bit efficiency: ${result.efficiency_vs_8bit}%</p>` : ''}
                ${entropyHtml}
                ${deepScanHtml}
                ${metaHtml}
                <button class="btn small download-btn" data-download-url="${result.download_url || ''}" data-filename="${result.compressed_filename || result.decompressed_filename}">Download</button>
            </div>
        `;
    } else {
        resultDiv.innerHTML = `
            <div class="result-error">
                <p><strong>✗ ${result.filename}</strong></p>
                <p class="error-text">${result.error}</p>
            </div>
        `;
    }

    return resultDiv;
}

//* Format byte values into human-readable units (B, KB, MB, GB)
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

//* ============================================================================
//* FILE UPLOAD & DOWNLOAD - Server communication
//* ============================================================================

//* Safely parse JSON responses from the server.
//* The previous implementation used response.json() directly, which crashes
//* when the backend returns HTML debug pages or malformed responses.
async function safeParseJson(response) {
    const contentType = response.headers.get('content-type') || '';
    const text = await response.text();

    if (contentType.includes('application/json') || text.trim().startsWith('{') || text.trim().startsWith('[')) {
        try {
            return JSON.parse(text);
        } catch (error) {
            console.warn('JSON parsing failed for server response:', error);
            throw new Error(`Invalid JSON response from server. ${error.message}. Response start: ${text.slice(0, 200)}`);
        }
    }

    const preview = text.replace(/\s+/g, ' ').trim().slice(0, 300);
    throw new Error(`Server returned non-JSON response (${response.status}). Response starts with: ${preview}`);
}

//* Upload files to server for compression/decompression
async function uploadFiles(endpoint, input, button, resultsContainer, resultsList) {
    //! Validate file selection
    if (!input || !input.files || input.files.length === 0) {
        alert('Please select files to upload first.');
        return;
    }

    const files = Array.from(input.files);
    console.debug(`Uploading ${files.length} file(s) to ${endpoint}`);

    //* Prepare FormData for multipart upload
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    //! Set loading state on button
    button.disabled = true;
    button.classList.add('loading');
    const originalLabel = button.textContent;
    button.innerHTML = `<span class="loading-spinner"></span>Processing...`;

    try {
        //! Send POST request to server
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        console.debug('Server response status:', response.status, 'content-type:', response.headers.get('content-type'));
        const data = await safeParseJson(response);
        console.debug('Received response from server', data);

        if (!response.ok) {
            const message = data?.error || data?.message || 'Server returned an error while processing files.';
            alert(`Error: ${message}`);
            return;
        }

        //! Render results for each file
        resultsList.innerHTML = '';
        data.results.forEach((result) => {
            resultsList.appendChild(buildResults(result));
        });

        //! Attach download handlers
        document.querySelectorAll('.download-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const filename = target.dataset.filename;
                const downloadUrl = target.dataset.downloadUrl;
                const b64Data = target.dataset.b64;

                if (downloadUrl) {
                    window.location.href = downloadUrl;
                    return;
                }

                if (b64Data && filename) {
                    downloadFile(b64Data, filename);
                }
            });
        });

        resultsContainer.style.display = 'block';
        input.value = '';
        updateUploadText(input.closest('.upload-box'), input.files);
    } catch (error) {
        console.error('Upload failed', error);
        alert(`Upload failed: ${error.message}`);
    } finally {
        //! Reset button state
        button.disabled = false;
        button.classList.remove('loading');
        button.innerHTML = originalLabel;
    }
}

//* Download file from base64-encoded data
function downloadFile(b64Data, filename) {
    //* Decode base64 to binary
    const binaryString = atob(b64Data);
    const bytes = new Uint8Array(binaryString.length);

    for (let i = 0; i < binaryString.length; i += 1) {
        bytes[i] = binaryString.charCodeAt(i);
    }

    //* Create blob and trigger download
    const blob = new Blob([bytes], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

//* ============================================================================
//* ACTION BUTTONS - Compress/Decompress and Clear Results
//* ============================================================================

function initActionButtons() {
    const compressBtn = document.getElementById('compress-btn');
    const decompressBtn = document.getElementById('decompress-btn');

    //! Compress button event listener
    if (compressBtn) {
        const input = document.getElementById('file-input');
        const resultsContainer = document.getElementById('results-container');
        const resultsList = document.getElementById('results-list');
        const clearResultsBtn = document.getElementById('clear-results');

        compressBtn.addEventListener('click', (event) => {
            event.preventDefault();
            uploadFiles('/compress', input, compressBtn, resultsContainer, resultsList);
        });

        if (clearResultsBtn) {
            clearResultsBtn.addEventListener('click', (event) => {
                event.preventDefault();
                resultsContainer.style.display = 'none';
                resultsList.innerHTML = '';
            });
        }
    }

    //! Decompress button event listener
    if (decompressBtn) {
        const input = document.getElementById('file-input');
        const resultsContainer = document.getElementById('results-container');
        const resultsList = document.getElementById('results-list');
        const clearResultsBtn = document.getElementById('clear-results');

        decompressBtn.addEventListener('click', (event) => {
            event.preventDefault();
            uploadFiles('/decompress', input, decompressBtn, resultsContainer, resultsList);
        });

        if (clearResultsBtn) {
            clearResultsBtn.addEventListener('click', (event) => {
                event.preventDefault();
                resultsContainer.style.display = 'none';
                resultsList.innerHTML = '';
            });
        }
    }
}

//* ============================================================================
//* INITIALIZATION - Setup all UI components
//* ============================================================================

//* Initialize all UI components
function initCommonUI() {
    initThemeToggle();
    initSidebarNav();
    initUploadBoxes();
    initActionButtons();
}

//! Run initialization when DOM is ready
document.addEventListener('DOMContentLoaded', initCommonUI);