function drawRectangle() {
    // Get the length and width values from user input
    const length = parseFloat(document.getElementById('length').value);
    const width = parseFloat(document.getElementById('width').value);

    // Validate input
    if (length <= 0 || width <= 0) {
        alert("Length and width must be positive numbers.");
        return;
    }

    // Get the rectangle container and clear any previous content
    const rectangleContainer = document.getElementById('rectangle-container');
    const rectangle = document.getElementById('rectangle');
    rectangle.innerHTML = '';
    rectangle.style.width = '';
    rectangle.style.height = '';
    const labels = document.querySelectorAll('.dimension-label');
    labels.forEach(label => label.remove());
    const panels = document.querySelectorAll('.large-panel, .rotated-large-panel');
    panels.forEach(panel => panel.remove());

    // Calculate scaled dimensions based on available viewport space
    const availableWidth = window.innerWidth * 0.6;
    const availableHeight = window.innerHeight * 0.6;
    const aspectRatio = width / length; // Calculate aspect ratio based on desired rotation
    let scaledWidth, scaledHeight;

    if (availableWidth / width < availableHeight / length) {
        scaledWidth = availableWidth;
        scaledHeight = availableWidth / aspectRatio; // Adjust height based on aspect ratio
    } else {
        scaledHeight = availableHeight;
        scaledWidth = availableHeight * aspectRatio; // Adjust width based on aspect ratio
    }

    // Set the dimensions of the rectangle
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

    // Calculate number of large panels that fit
    const largePanelsAlongLength = Math.floor(length / largePanelLength);
    const largePanelsAlongWidth = Math.floor(width / largePanelWidth);
    const remainingArea = (length * width) - (largePanelsAlongLength * largePanelsAlongWidth * largePanelArea);
    
    // Calculate remaining length and width for rotated panels
    let remainingLength = 0;
    let remainingWidth = 0;
    
    if (remainingArea > 0) {
        remainingLength = Math.round((length-(largePanelLength*largePanelsAlongLength))*100) / 100;
        if (remainingLength < rotatedLargePanelLength) {
            remainingLength = 0;
        }
        else {
            remainingWidth = width;
        }
    }

    // Calculate number of rotated large panels that fit
    const rotatedLargePanelsAlongLength = Math.floor(remainingLength / rotatedLargePanelLength);
    const rotatedLargePanelsAlongWidth = Math.floor(remainingWidth / rotatedLargePanelWidth);
    console.log("remaininglength", remainingLength);
    console.log("remainingWidth", remainingWidth);
    console.log("rotatedLargePanelsAlongLength", rotatedLargePanelsAlongLength);
    console.log("rotatedLargePanelsAlongWidth", rotatedLargePanelsAlongWidth);

    // Draw large panels
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

    // Draw rotated large panels
    const rotatedLargePanelContainer = document.createElement('div');
    rotatedLargePanelContainer.style.position = 'absolute';
    rotatedLargePanelContainer.style.width = '100%';
    rotatedLargePanelContainer.style.height = '100%';
    let rotatedLargePanelCount = 0;

    // Calculate the starting position for rotated panels
    const startRow = largePanelsAlongLength;
    //const startRow = largePanelsAlongLength;
    const startCol = 0;

    for (let row = startRow; row < startRow + rotatedLargePanelsAlongLength; row++) {
        for (let col = startCol; col < startCol + rotatedLargePanelsAlongWidth; col++) {
            if (rotatedLargePanelCount >= (rotatedLargePanelsAlongLength * rotatedLargePanelsAlongWidth)) {
                break;
            }

            const rotatedLargePanel = document.createElement('div');
            rotatedLargePanel.className = 'rotated-large-panel';
            rotatedLargePanel.style.width = (rotatedLargePanelWidth / width) * scaledWidth + 'px';
            rotatedLargePanel.style.height = (rotatedLargePanelLength / length) * scaledHeight + 'px';
            //rotatedLargePanel.style.top = (row * (rotatedLargePanelLength / length) * scaledHeight) + 'px';
            rotatedLargePanel.style.top = (largePanelLength / length) * scaledHeight + 'px';
            rotatedLargePanel.style.left = (col * (rotatedLargePanelWidth / width) * scaledWidth) + 'px';
            rotatedLargePanelContainer.appendChild(rotatedLargePanel);
            rotatedLargePanelCount++;
        }
    }

    // Display the count of large and rotated large panels
    const resultContainer = document.createElement('div');
    resultContainer.textContent = `Number of Large Panels that can fit: ${largePanelCount}`;
    resultContainer.style.marginTop = '10px';

    const rotatedResultContainer = document.createElement('div');
    rotatedResultContainer.textContent = `Number of Rotated Large Panels that can fit: ${rotatedLargePanelCount}`;
    rotatedResultContainer.style.marginTop = '10px';

    // Append panels and results to the rectangle container
    rectangle.appendChild(largePanelContainer);
    rectangle.appendChild(rotatedLargePanelContainer);
    rectangleContainer.appendChild(resultContainer);
    rectangleContainer.appendChild(rotatedResultContainer);

    // Create and append dimension labels
    const widthLabel = document.createElement('div');
    widthLabel.className = 'dimension-label width-label';
    widthLabel.textContent = `Width: ${width}`;

    const lengthLabel = document.createElement('div');
    lengthLabel.className = 'dimension-label height-label';
    lengthLabel.textContent = `Length: ${length}`;

    rectangleContainer.appendChild(widthLabel);
    rectangleContainer.appendChild(lengthLabel);
}
