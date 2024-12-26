// Show the spinner and message initially
document.addEventListener("DOMContentLoaded", () => {
    const syncStatus = document.getElementById("sync-status");
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");

    // Show spinner and message
    syncStatus.style.display = "flex";

    // Function to poll the backend for sync status
    const checkSyncStatus = async () => {
        try {
            const response = await fetch("/sync-status"); // Endpoint for sync status
            const data = await response.json();

            if (!data.ongoing) {
                // Hide the spinner and show the success message
                spinner.style.display = "none";
                syncText.textContent = "😊 Background Sync Completed!";
                syncText.style.color = "green";

                // Stop polling once sync is complete
                clearInterval(syncInterval);
            }
        } catch (error) {
            console.error("Error checking sync status:", error);
        }
    };

    // Poll the sync status every 2 seconds
    const syncInterval = setInterval(checkSyncStatus, 2000);
});

function startBackgroundSync() {
    // Show the spinner and status
    document.getElementById("sync-status").style.display = "inline-flex";
    document.getElementById("spinner").style.display = "inline-block";
    document.getElementById("sync-text").textContent = "Background Sync Ongoing";

    // Send the refresh request
    fetch('/refresh')
        .then(response => {
            if (response.ok) {
                pollSyncStatus(); // Start polling the sync status
            } else {
                handleSyncError();
            }
        })
        .catch(handleSyncError);
}

function pollSyncStatus() {
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");

    const interval = setInterval(() => {
        fetch('/sync-status')
            .then(response => response.json())
            .then(data => {
                if (!data.ongoing) {
                    clearInterval(interval); // Stop polling
                    spinner.style.display = "none"; // Hide the spinner
                    syncText.innerHTML = "😊 Background Sync Completed!";
                }
            })
            .catch(error => {
                console.error('Error checking sync status:', error);
                clearInterval(interval); // Stop polling on error
                spinner.style.display = "none";
                syncText.textContent = "Background Sync Failed!";
            });
    }, 1000); // Poll every second
}

function handleSyncError() {
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");
    spinner.style.display = "none";
    syncText.textContent = "Background Sync Failed!";
}
