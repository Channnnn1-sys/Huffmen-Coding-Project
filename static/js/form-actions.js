//* ============================================================================
//* LEGACY FORM ACTIONS - Result rendering and file operations
//* Note: These functions are also in app.js; this file is for legacy compatibility
//* ============================================================================

//* Format byte values into human-readable units (B, KB, MB, GB)
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

//* Build result DOM element with compression/decompression details
function buildResults(result) {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'result-item';

    if (result.success) {
        //* Format optional data sections
        const savedText = result.saved_bytes !== undefined
            ? `Saved: ${formatBytes(result.saved_bytes)}`
            : '';

        //! Display top 5 most frequent bytes in file
        const topSymbols = result.top_symbols && result.top_symbols.length
            ? `<div class="result-meta">${result.top_symbols.map(symbol => `<span class="tag">Byte ${symbol.byte} • ${symbol.frequency}× • ${symbol.code_length} bits</span>`).join(' ')}</div>`
            : '';

        //! Warn if file is already highly compressed
        const entropyHtml = result.entropy_warning
            ? `<p class="result-note">⚠️ ${result.entropy_warning}</p>`
            : '';

        //! Show deep scan for Office files
        const deepScanHtml = result.deep_scan && result.deep_scan.office_archive
            ? `<div class="result-subnote"><p><strong>Deep Scan:</strong> ${result.deep_scan.office_message}</p><p>${result.deep_scan.office_xml_files} XML text layers detected (${result.deep_scan.office_xml_ratio}% of archive).</p></div>`
            : '';

        resultDiv.innerHTML = `
            <div class="result-success">
                <p><strong>✓ ${result.filename}</strong></p>
                ${result.original_size ? `<p>Original: ${formatBytes(result.original_size)}</p>` : ''}
                ${result.compressed_size ? `<p>Compressed: ${formatBytes(result.compressed_size)}</p>` : ''}
                ${result.decompressed_size ? `<p>Restored Size: ${formatBytes(result.decompressed_size)}</p>` : ''}
                ${result.compression_ratio ? `<p>Ratio: ${result.compression_ratio}%</p>` : ''}
                ${savedText ? `<p>${savedText}</p>` : ''}
                ${result.average_bits_per_symbol ? `<p>Avg bits/symbol: ${result.average_bits_per_symbol}</p>` : ''}
                ${result.efficiency_vs_8bit ? `<p>8-bit efficiency: ${result.efficiency_vs_8bit}%</p>` : ''}
                ${entropyHtml}
                ${deepScanHtml}
                ${topSymbols}
                <button class="btn small download-btn" data-b64="${result.data_b64}" data-filename="${result.compressed_filename || result.decompressed_filename}">Download</button>
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
//* FILE UPLOAD & DOWNLOAD - Server communication
//* ============================================================================

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

        const data = await response.json();
        console.debug('Received response from server', data);

        if (!response.ok) {
            const message = data?.error || 'Server returned an error while processing files.';
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
                const b64Data = target.dataset.b64;
                const filename = target.dataset.filename;
                if (b64Data && filename) {
                    downloadFile(b64Data, filename);
                }
            });
        });

        resultsContainer.style.display = 'block';
        input.value = '';
        const uploadBox = input.closest('.upload-box');
        if (uploadBox && typeof updateUploadText === 'function') {
            updateUploadText(uploadBox, input.files);
        }
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

//! Initialize on page load
document.addEventListener('DOMContentLoaded', initActionButtons);
