// Show summarize history when button is clicked
document.addEventListener('DOMContentLoaded', function() {
    const showHistoryBtn = document.getElementById('show-history-btn');
    const historyContainer = document.getElementById('history-container');

    showHistoryBtn.addEventListener('click', function() {
        historyContainer.classList.toggle('show');
    });
});

// Analyze text from the textarea
document.getElementById('analyze-btn').addEventListener('click', async function() {
    let text = document.getElementById('input-text').value;

    if (!text) {
        alert('Please enter or paste text to analyze.');
        return;
    }

    // Send text to backend for analysis
    let response = await fetch('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    });

    if (response.ok) {
        let result = await response.json();
        displayResults(result);
    } else {
        let errorMsg = await response.json();
        alert(errorMsg.error || 'Error analyzing the text.');
    }
});

// Display analysis results
function displayResults(result) {
    document.getElementById('summary-text').innerText = result.summary;
    document.getElementById('keywords-text').innerText = result.keywords.join(', ');

    let topicsList = document.getElementById('topics-list');
    topicsList.innerHTML = '';
    result.topics.forEach(topic => {
        let li = document.createElement('li');
        li.innerText = topic;
        topicsList.appendChild(li);
    });

    document.getElementById('sentiment-text').innerText = result.sentiment;
}

// Handle PDF file upload and process all features
document.getElementById('upload-form').addEventListener('submit', async function(event) {
    event.preventDefault();  // Prevent the default form submission behavior

    let fileInput = document.getElementById('file-input');
    if (fileInput.files.length === 0) {
        alert('Please select a file to upload.');
        return;
    }

    let formData = new FormData();
    formData.append('file', fileInput.files[0]);

    // Send file to backend for processing
    let response = await fetch('/upload', {
        method: 'POST',
        body: formData
    });

    if (response.status === 401) {
        alert('You need to log in first to access the file upload feature.');
        return;
    }

    if (response.ok) {
        // Create a link to download the summarized PDF
        let blob = await response.blob();
        let url = window.URL.createObjectURL(blob);

        // Show the download button and set its href attribute
        let downloadLink = document.getElementById('download-link');
        downloadLink.style.display = 'block';
        downloadLink.href = url;
        downloadLink.download = 'summarized_output.pdf';
        alert('File summarized and ready for download.');
    } else {
        let errorMsg = await response.json();
        alert(errorMsg.error || 'Error uploading or summarizing the file.');
    }
});

// Clipboard paste functionality for text input
document.getElementById('paste-btn').addEventListener('click', function() {
    navigator.clipboard.readText().then(text => {
        document.getElementById('input-text').value = text;
    }).catch(err => {
        alert('Failed to read clipboard contents: ', err);
    });
});