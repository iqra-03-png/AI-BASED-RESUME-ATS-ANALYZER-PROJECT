document.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.querySelector("#resume-file");
  const fileName = document.querySelector("#file-name");
  const uploadBox = document.querySelector(".upload-box");
  const description = document.querySelector("#job-description");
  const characterCount = document.querySelector("#char-count");
  const analysisForm = document.querySelector(".analysis-form");

  const showFile = (file) => {
    if (!fileName || !file) return;
    fileName.textContent = file.name;
  };

  if (fileInput) {
    fileInput.addEventListener("change", () => showFile(fileInput.files[0]));
  }

  if (uploadBox && fileInput) {
    ["dragenter", "dragover"].forEach((eventName) => {
      uploadBox.addEventListener(eventName, (event) => {
        event.preventDefault();
        uploadBox.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      uploadBox.addEventListener(eventName, (event) => {
        event.preventDefault();
        uploadBox.classList.remove("is-dragging");
      });
    });
    uploadBox.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      if (!file) return;
      const extension = file.name.split(".").pop().toLowerCase();
      if (!["pdf", "docx"].includes(extension)) {
        fileName.textContent = "Choose a PDF or DOCX resume";
        return;
      }
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      showFile(file);
    });
  }

  if (description && characterCount) {
    const updateCount = () => {
      characterCount.textContent = `${description.value.length.toLocaleString()} / 20,000`;
    };
    description.addEventListener("input", updateCount);
    updateCount();
  }

  if (analysisForm) {
    analysisForm.addEventListener("submit", () => {
      const button = document.querySelector("#analyze-button");
      if (!button) return;
      button.disabled = true;
      button.querySelector(".button-label").hidden = true;
      button.querySelector(".loading-label").hidden = false;
    });
  }
});
