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

    // Clear result containers
    const resultContainers = document.querySelectorAll('.result-container');
    resultContainers.forEach(container => container.remove());

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
        remainingLength = Math.round((length - (largePanelLength * largePanelsAlongLength)) * 100) / 100;
        if (remainingLength < rotatedLargePanelLength) {
            remainingLength = 0;
        } else {
            remainingWidth = width;
        }
    }

    // Calculate number of rotated large panels that fit
    const rotatedLargePanelsAlongLength = Math.floor(remainingLength / rotatedLargePanelLength);
    const rotatedLargePanelsAlongWidth = Math.floor(remainingWidth / rotatedLargePanelWidth);

    spaceUtilizedPercentageA = ((largePanelsAlongLength * largePanelsAlongWidth * largePanelArea) + (rotatedLargePanelsAlongLength * rotatedLargePanelsAlongWidth * rotatedLargePanelArea)) / (length * width);
    console.log("Total Space Utilized A: ", spaceUtilizedPercentageA * 100);

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
            rotatedLargePanel.style.top = (largePanelLength / length) * largePanelsAlongLength * scaledHeight + 'px';
            rotatedLargePanel.style.left = (col * (rotatedLargePanelWidth / width) * scaledWidth) + 'px';
            rotatedLargePanelContainer.appendChild(rotatedLargePanel);
            rotatedLargePanelCount++;
        }
    }

    // Display the count of large and rotated large panels
    const resultContainer = document.createElement('div');
    resultContainer.className = 'result-container';
    resultContainer.textContent = `Number of Large Panels that can fit: ${largePanelCount}`;
    resultContainer.style.marginTop = '10px';

    const rotatedResultContainer = document.createElement('div');
    rotatedResultContainer.className = 'result-container';
    rotatedResultContainer.textContent = `Number of Rotated Large Panels that can fit: ${rotatedLargePanelCount}`;
    rotatedResultContainer.style.marginTop = '10px';

    // Display the remaining length and width
    const remainingLengthContainer = document.createElement('div');
    remainingLengthContainer.className = 'result-container';
    let outRemainingLength = length - (largePanelsAlongLength * largePanelLength) - (rotatedLargePanelsAlongLength * rotatedLargePanelLength);
    remainingLengthContainer.textContent = `Remaining Length: ${Math.round(outRemainingLength * 100) / 100}`;
    remainingLengthContainer.style.marginTop = '10px';

    const remainingWidthContainer = document.createElement('div');
    remainingWidthContainer.className = 'result-container';
    remainingWidthContainer.textContent = `Remaining Width: ${Math.round((width - (largePanelsAlongWidth * largePanelWidth)) * 100) / 100}`;
    remainingWidthContainer.style.marginTop = '10px';

    // Append panels and results to the rectangle container
    rectangle.appendChild(largePanelContainer);
    rectangle.appendChild(rotatedLargePanelContainer);
    rectangleContainer.appendChild(resultContainer);
    rectangleContainer.appendChild(rotatedResultContainer);
    rectangleContainer.appendChild(remainingLengthContainer);
    rectangleContainer.appendChild(remainingWidthContainer);

    // Create and append dimension labels
    const widthLabel = document.createElement('div');
    widthLabel.className = 'dimension-label width-label';
    widthLabel.textContent = `Width: ${width}`;

    const lengthLabel = document.createElement('div');
    lengthLabel.className = 'dimension-label height-label';
    lengthLabel.textContent = `Length: ${length}`;

    rectangleContainer.appendChild(widthLabel);
    rectangleContainer.appendChild(lengthLabel);

    // REDO for Second Variant
    lengthB = width;
    widthB = length;

    // Get the rectangle container and clear any previous content
    const rectangleContainerB = document.getElementById('rectangle-containerB');
    const rectangleB = document.getElementById('rectangleB');
    rectangleB.innerHTML = '';
    rectangleB.style.width = '';
    rectangleB.style.height = '';
    const labelsB = document.querySelectorAll('.dimension-labelB');
    labelsB.forEach(label => label.remove());
    const panelsB = document.querySelectorAll('.large-panelB, .rotated-large-panelB');
    panelsB.forEach(panel => panel.remove());

    // Clear result containers
    const resultContainersB = document.querySelectorAll('.result-containerB');
    resultContainersB.forEach(container => container.remove());

    // Calculate scaled dimensions based on available viewport space
    const availableWidthB = window.innerWidth * 0.6;
    const availableHeightB = window.innerHeight * 0.6;
    const aspectRatioB = widthB / lengthB; // Calculate aspect ratio based on desired rotation
    let scaledWidthB, scaledHeightB;

    if (availableWidthB / widthB < availableHeightB / lengthB) {
        scaledWidthB = availableWidthB;
        scaledHeightB = availableWidthB / aspectRatioB; // Adjust height based on aspect ratio
    } else {
        scaledHeightB = availableHeightB;
        scaledWidthB = availableHeightB * aspectRatioB; // Adjust width based on aspect ratio
    }

    // Set the dimensions of the rectangle
    rectangleB.style.width = scaledWidthB + 'px';
    rectangleB.style.height = scaledHeightB + 'px';

    // Define panel dimensions
    const largePanelLengthB = 2.1;
    const largePanelWidthB = 1.2;
    const rotatedLargePanelLengthB = 1.2;
    const rotatedLargePanelWidthB = 2.1;
    const smallPanelLengthB = 1.2;
    const smallPanelWidthB = 1.2;

    // Calculate area of panels
    const largePanelAreaB = largePanelLengthB * largePanelWidthB;
    const rotatedLargePanelAreaB = rotatedLargePanelLengthB * rotatedLargePanelWidthB;

    // Calculate number of large panels that fit
    const largePanelsAlongLengthB = Math.floor(lengthB / largePanelLengthB);
    const largePanelsAlongWidthB = Math.floor(widthB / largePanelWidthB);
    const remainingAreaB = (lengthB * widthB) - (largePanelsAlongLengthB * largePanelsAlongWidthB * largePanelAreaB);
    
    // Calculate remaining length and width for rotated panels
    let remainingLengthB = 0;
    let remainingWidthB = 0;
    
    if (remainingAreaB > 0) {
        remainingLengthB = Math.round((lengthB - (largePanelLengthB * largePanelsAlongLengthB)) * 100) / 100;
        if (remainingLengthB < rotatedLargePanelLengthB) {
            remainingLengthB = 0;
        } else {
            remainingWidthB = widthB;
        }
    }

    // Calculate number of rotated large panels that fit
    const rotatedLargePanelsAlongLengthB = Math.floor(remainingLengthB / rotatedLargePanelLengthB);
    const rotatedLargePanelsAlongWidthB = Math.floor(remainingWidthB / rotatedLargePanelWidthB);

    spaceUtilizedPercentageB = ((largePanelsAlongLengthB * largePanelsAlongWidthB * largePanelAreaB) + (rotatedLargePanelsAlongLengthB * rotatedLargePanelsAlongWidthB * rotatedLargePanelAreaB)) / (lengthB * widthB);
    console.log("Total Space Utilized B: ", spaceUtilizedPercentageB * 100);

    // Draw large panels
    const largePanelContainerB = document.createElement('div');
    largePanelContainerB.style.position = 'absolute';
    largePanelContainerB.style.width = '100%';
    largePanelContainerB.style.height = '100%';
    let largePanelCountB = 0;

    for (let row = 0; row < largePanelsAlongLengthB; row++) {
        for (let col = 0; col < largePanelsAlongWidthB; col++) {
            if (largePanelCountB >= (largePanelsAlongLengthB * largePanelsAlongWidthB)) {
                break;
            }

            const largePanelB = document.createElement('div');
            largePanelB.className = 'large-panelB';
            largePanelB.style.width = (largePanelWidthB / widthB) * scaledWidthB + 'px';
            largePanelB.style.height = (largePanelLengthB / lengthB) * scaledHeightB + 'px';
            largePanelB.style.top = (row * (largePanelLengthB / lengthB) * scaledHeightB) + 'px';
            largePanelB.style.left = (col * (largePanelWidthB / widthB) * scaledWidthB) + 'px';
            largePanelContainerB.appendChild(largePanelB);
            largePanelCountB++;
        }
    }

    // Draw rotated large panels
    const rotatedLargePanelContainerB = document.createElement('div');
    rotatedLargePanelContainerB.style.position = 'absolute';
    rotatedLargePanelContainerB.style.width = '100%';
    rotatedLargePanelContainerB.style.height = '100%';
    let rotatedLargePanelCountB = 0;

    // Calculate the starting position for rotated panels
    const startRowB = largePanelsAlongLengthB;
    const startColB = 0;

    for (let row = startRowB; row < startRowB + rotatedLargePanelsAlongLengthB; row++) {
        for (let col = startColB; col < startColB + rotatedLargePanelsAlongWidthB; col++) {
            if (rotatedLargePanelCountB >= (rotatedLargePanelsAlongLengthB * rotatedLargePanelsAlongWidthB)) {
                break;
            }

            const rotatedLargePanelB = document.createElement('div');
            rotatedLargePanelB.className = 'rotated-large-panelB';
            rotatedLargePanelB.style.width = (rotatedLargePanelWidthB / widthB) * scaledWidthB + 'px';
            rotatedLargePanelB.style.height = (rotatedLargePanelLengthB / lengthB) * scaledHeightB + 'px';
            rotatedLargePanelB.style.top = (largePanelLengthB / lengthB) * largePanelsAlongLengthB * scaledHeightB + 'px';
            rotatedLargePanelB.style.left = (col * (rotatedLargePanelWidthB / widthB) * scaledWidthB) + 'px';
            rotatedLargePanelContainerB.appendChild(rotatedLargePanelB);
            rotatedLargePanelCountB++;
        }
    }

    // Display the count of large and rotated large panels
    const resultContainerB = document.createElement('div');
    resultContainerB.className = 'result-containerB';
    resultContainerB.textContent = `Number of Large Panels that can fit B: ${largePanelCountB}`;
    resultContainerB.style.marginTop = '10px';

    const rotatedResultContainerB = document.createElement('div');
    rotatedResultContainerB.className = 'result-containerB';
    rotatedResultContainerB.textContent = `Number of Rotated Large Panels that can fit B: ${rotatedLargePanelCountB}`;
    rotatedResultContainerB.style.marginTop = '10px';

    // Display the remaining length and width
    const remainingLengthContainerB = document.createElement('div');
    remainingLengthContainerB.className = 'result-containerB';
    let outRemainingLengthB = lengthB - (largePanelsAlongLengthB * largePanelLengthB) - (rotatedLargePanelsAlongLengthB * rotatedLargePanelLengthB);
    remainingLengthContainerB.textContent = `Remaining Length B: ${Math.round(outRemainingLengthB * 100) / 100}`;
    remainingLengthContainerB.style.marginTop = '10px';

    const remainingWidthContainerB = document.createElement('div');
    remainingWidthContainerB.className = 'result-containerB';
    remainingWidthContainerB.textContent = `Remaining Width B: ${Math.round((widthB - (largePanelsAlongWidthB * largePanelWidthB)) * 100) / 100}`;
    remainingWidthContainerB.style.marginTop = '10px';

    // Append panels and results to the rectangle container
    rectangleB.appendChild(largePanelContainerB);
    rectangleB.appendChild(rotatedLargePanelContainerB);
    rectangleContainerB.appendChild(resultContainerB);
    rectangleContainerB.appendChild(rotatedResultContainerB);
    rectangleContainerB.appendChild(remainingLengthContainerB);
    rectangleContainerB.appendChild(remainingWidthContainerB);

    // Create and append dimension labels
    const widthLabelB = document.createElement('div');
    widthLabelB.className = 'dimension-labelB width-labelB';
    widthLabelB.textContent = `Width B: ${widthB}`;

    const lengthLabelB = document.createElement('div');
    lengthLabelB.className = 'dimension-labelB height-labelB';
    lengthLabelB.textContent = `Length B: ${lengthB}`;

    rectangleContainerB.appendChild(widthLabelB);
    rectangleContainerB.appendChild(lengthLabelB);

}
