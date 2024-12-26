// JavaScript for drawing rectangle and panels

function drawRectangle() {
    // Get the length and width values
    const length = parseFloat(document.getElementById('length').value);
    const width = parseFloat(document.getElementById('width').value);

    // Validate input
    if (length <= 0 || width <= 0) {
        alert("Length and width must be positive numbers.");
        return;
    }

    // Get the rectangle container div
    const rectangleContainer = document.getElementById('rectangle-container');
    const rectangle = document.getElementById('rectangle');

    // Clear any previous rectangle, labels, and panels
    rectangle.innerHTML = '';
    rectangle.style.width = '';
    rectangle.style.height = '';
    const labels = document.querySelectorAll('.dimension-label');
    labels.forEach(label => label.remove());
    const panels = document.querySelectorAll('.large-panel, .rotated-large-panel');
    panels.forEach(panel => panel.remove());

    // Calculate the aspect ratio of the rectangle
    const aspectRatio = length / width;

    // Get the available dimensions (60% of the viewport)
    const availableWidth = window.innerWidth * 0.6;
    const availableHeight = window.innerHeight * 0.6;

    // Calculate the scaled dimensions of the rectangle
    let scaledWidth, scaledHeight;
    if (availableWidth / width < availableHeight / length) {
        scaledWidth = availableWidth;
        scaledHeight = availableWidth * aspectRatio;
    } else {
        scaledHeight = availableHeight;
        scaledWidth = availableHeight / aspectRatio;
    }

    // Set the rectangle dimensions
    rectangle.style.width = scaledWidth + 'px';
    rectangle.style.height = scaledHeight + 'px';

    // Define panel dimensions
    const largePanelLength = 2.1;
    const largePanelWidth = 1.2;
    const rotatedLargePanelLength = 1.2;
    const rotatedLargePanelWidth = 2.1;
    const smallPanelLength = 1.2;
    const smallPanelWidth = 1.2;

    // Calculate area of panels
    const largePanelArea = largePanelLength * largePanelWidth;
    const rotatedLargePanelArea = rotatedLargePanelLength * rotatedLargePanelWidth;

    // Calculate number of panels that can fit
    const largePanelsAlongLength = Math.floor(length / largePanelLength);
    const largePanelsAlongWidth = Math.floor(width / largePanelWidth);
 
    // Draw LargePanel inside the rectangle
    const largePanelContainer = document.createElement('div');
    largePanelContainer.style.position = 'absolute';
    largePanelContainer.style.width = '100%';
    largePanelContainer.style.height = '100%';

    let largePanelCount = 0;

    for (let row = 0; row < largePanelsAlongLength; row++) {
        for (let col = 0; col < largePanelsAlongWidth; col++) {
            if (largePanelCount >= (largePanelsAlongLength * largePanelsAlongWidth)) {
                break;
            }

            const largePanel = document.createElement('div');
            largePanel.className = 'large-panel';
            largePanel.style.width = (largePanelWidth / width) * scaledWidth + 'px';
            largePanel.style.height = (largePanelLength / length) * scaledHeight + 'px';
            largePanel.style.top = (row * (largePanelLength / length) * scaledHeight) + 'px';
            largePanel.style.left = (col * (largePanelWidth / width) * scaledWidth) + 'px';
            largePanelContainer.appendChild(largePanel);

            largePanelCount++;
        }
    }

    // Calculate remaining space for RotatedLargePanel
    const remainingArea = (length * width) - (largePanelCount * largePanelArea);
    var remainingLength = Math.round((length-(largePanelLength*largePanelsAlongLength))*100) / 100;
    var remainingWidth = 0;
    if (remainingLength < rotatedLargePanelLength) {
        remainingLength = 0;
    }
    else {
        remainingWidth = width;
    }

    // Calculate number of rotated panels that can fit in the remaining space
    const rotatedLargePanelsAlongLength = Math.floor(remainingLength / rotatedLargePanelLength);
    const rotatedLargePanelsAlongWidth = Math.floor(remainingWidth / rotatedLargePanelWidth);
    console.log("remaininglength", remainingLength);
    console.log("remainingWidth", remainingWidth);
    console.log("rotatedLargePanelsAlongLength", rotatedLargePanelsAlongLength);
    console.log("rotatedLargePanelsAlongWidth", rotatedLargePanelsAlongWidth);

    // Draw RotatedLargePanel inside the remaining space
    const rotatedLargePanelContainer = document.createElement('div');
    rotatedLargePanelContainer.style.position = 'absolute';
    rotatedLargePanelContainer.style.width = '100%';
    rotatedLargePanelContainer.style.height = '100%';

    let rotatedLargePanelCount = 0;

    for (let row = 0; row < rotatedLargePanelsAlongLength; row++) {
        for (let col = 0; col < rotatedLargePanelsAlongWidth; col++) {
            if (rotatedLargePanelCount >= (rotatedLargePanelsAlongLength * rotatedLargePanelsAlongWidth)) {
                break;
            }

            const rotatedLargePanel = document.createElement('div');
            rotatedLargePanel.className = 'rotated-large-panel';
            rotatedLargePanel.style.width = (rotatedLargePanelWidth / width) * scaledWidth + 'px';
            rotatedLargePanel.style.height = (rotatedLargePanelLength / length) * scaledHeight + 'px';
            rotatedLargePanel.style.top = (row * (rotatedLargePanelLength / length) * scaledHeight) + 'px';
            rotatedLargePanel.style.left = (col * (rotatedLargePanelWidth / width) * scaledWidth) + 'px';
            rotatedLargePanelContainer.appendChild(rotatedLargePanel);

            rotatedLargePanelCount++;
        }
    }

    // Display result
    const resultContainer = document.createElement('div');
    resultContainer.textContent = `Number of Large Panels that can fit: ${largePanelCount}`;
    resultContainer.style.marginTop = '10px';

    const rotatedResultContainer = document.createElement('div');
    rotatedResultContainer.textContent = `Number of Rotated Large Panels that can fit: ${rotatedLargePanelCount}`;
    rotatedResultContainer.style.marginTop = '10px';

    // Append the panels and results to the container
    rectangle.appendChild(largePanelContainer);
    rectangle.appendChild(rotatedLargePanelContainer);
    rectangleContainer.appendChild(resultContainer);
    rectangleContainer.appendChild(rotatedResultContainer);

    // Create dimension labels
    const widthLabel = document.createElement('div');
    widthLabel.className = 'dimension-label width-label';
    widthLabel.textContent = `Width: ${width}`;

    const lengthLabel = document.createElement('div');
    lengthLabel.className = 'dimension-label height-label';
    lengthLabel.textContent = `Length: ${length}`;

    // Append dimension labels to the container
    rectangleContainer.appendChild(widthLabel);
    rectangleContainer.appendChild(lengthLabel);
}
