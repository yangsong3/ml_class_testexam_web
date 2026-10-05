const questionForm = document.querySelector(".admin-question-form");
const selectedUploadFiles = new Map();
const choiceRichEditors = new Map();

if (questionForm) {
  questionForm.querySelectorAll("input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file) {
        selectedUploadFiles.set(input.name, file);
      } else {
        selectedUploadFiles.delete(input.name);
      }
    });
  });
  questionForm.addEventListener("formdata", (event) => {
    selectedUploadFiles.forEach((file, name) => {
      event.formData.delete(name);
      event.formData.append(name, file, file.name);
    });
  });
  questionForm.querySelectorAll("[data-clear-choice-image]").forEach((button) => {
    const index = button.dataset.clearChoiceImage;
    const input = questionForm.querySelector(`input[name='choice_image_${index}']`);
    const updateButton = () => {
      button.disabled = !selectedUploadFiles.has(input.name);
    };
    input.addEventListener("change", updateButton);
    button.addEventListener("click", () => {
      input.value = "";
      selectedUploadFiles.delete(input.name);
      updateButton();
    });
  });
}

if (questionForm?.hasAttribute("data-id-recommendations")) {
  const categorySelect = questionForm.querySelector("select[name='category']");
  const identifierInput = questionForm.querySelector("input[name='identifier']");
  let lastRecommendation = identifierInput.dataset.lastRecommendation || "";

  categorySelect.addEventListener("change", () => {
    const selectedOption = categorySelect.options[categorySelect.selectedIndex];
    const nextRecommendation = selectedOption.dataset.recommendedId || "";
    const currentIdentifier = identifierInput.value.trim();

    if (!currentIdentifier || currentIdentifier === lastRecommendation) {
      identifierInput.value = nextRecommendation;
    }
    lastRecommendation = nextRecommendation;
    identifierInput.dataset.lastRecommendation = nextRecommendation;
  });
}

if (questionForm?.hasAttribute("data-question-type-controls")) {
  const typeSelect = questionForm.querySelector("select[name='question_type']");
  const choiceFields = questionForm.querySelector("[data-choice-fields]");
  const shortAnswerFields = questionForm.querySelector("[data-short-answer-fields]");
  const choiceInputs = choiceFields.querySelectorAll("input[name^='choice_'][type='text']");
  const textAnswers = shortAnswerFields.querySelector("textarea[name='text_answers']");

  const updateQuestionType = () => {
    const isShortAnswer = typeSelect.value === "short_answer";
    choiceFields.hidden = isShortAnswer;
    shortAnswerFields.hidden = !isShortAnswer;
    choiceInputs.forEach((input) => {
      input.required = !isShortAnswer;
    });
    textAnswers.required = isShortAnswer;
  };

  typeSelect.addEventListener("change", updateQuestionType);
  updateQuestionType();
}

const richEditorContainer = questionForm?.querySelector("[data-rich-question-editor]");

if (richEditorContainer && window.Quill) {
  const BlockEmbed = window.Quill.import("blots/block/embed");
  const storedImageUrl = (slot) =>
    richEditorContainer.getAttribute(`data-image-${slot}`) || "";
  const imageUrls = new Map(
    Array.from({ length: 5 }, (_, slot) => [
      slot,
      storedImageUrl(slot),
    ]).filter(([, url]) => url)
  );

  class QuestionImageBlot extends BlockEmbed {
    static blotName = "questionImage";
    static tagName = "figure";
    static className = "question-image-embed";

    static create(value) {
      const node = super.create();
      const image = document.createElement("img");
      const slot = typeof value === "object" ? value.slot : value;
      const imageUrl =
        (typeof value === "object" ? value.url : "") ||
        imageUrls.get(Number(slot));
      image.src = imageUrl || "";
      image.alt = `문제 참고 이미지 ${Number(slot) + 1}`;
      node.dataset.slot = String(slot);
      node.append(image);
      return node;
    }

    static value(node) {
      return { slot: Number(node.dataset.slot) };
    }
  }

  window.Quill.register(QuestionImageBlot);
  const editorElement = richEditorContainer.querySelector("[data-rich-editor]");
  const textInput = richEditorContainer.querySelector("[data-rich-question-text]");
  const documentInput = richEditorContainer.querySelector("[data-rich-question-document]");
  const imageManager = richEditorContainer.querySelector("[data-content-image-manager]");
  const addImageButton = richEditorContainer.querySelector("[data-add-content-image]");
  const imageInputs = Array.from(
    richEditorContainer.querySelectorAll("[data-content-image-input]")
  );
  const existingSlots = new Set(
    Array.from({ length: 5 }, (_, slot) => slot).filter(
      (slot) => storedImageUrl(slot)
    )
  );
  let selectedRange = { index: 0, length: 0 };
  let previewTimer;
  let previewQueue = Promise.resolve();

  const quill = new window.Quill(editorElement, {
    theme: "snow",
    placeholder: "문제 내용을 입력하세요.",
    formats: [
      "bold", "italic", "underline", "header", "list", "align", "questionImage",
    ],
    modules: {
      toolbar: [
        ["bold", "italic", "underline"],
        [{ header: [1, 2, 3, false] }],
        [{ list: "ordered" }, { list: "bullet" }],
        [{ align: [] }],
        ["clean"],
      ],
    },
  });

  const imageOperations = () => {
    const images = [];
    let index = 0;
    quill.getContents().ops.forEach((operation) => {
      const imageValue = operation.insert?.questionImage;
      if (imageValue !== undefined) {
        const slot = typeof imageValue === "object" ? imageValue.slot : imageValue;
        images.push({ slot: Number(slot), index });
      }
      index += typeof operation.insert === "string" ? operation.insert.length : 1;
    });
    return images;
  };

  const syncRemovalInputs = (activeSlots) => {
    richEditorContainer.querySelectorAll("[data-remove-content-image]").forEach(
      (input) => input.remove()
    );
    existingSlots.forEach((slot) => {
      if (!activeSlots.has(slot)) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "remove_content_images";
        input.value = String(slot);
        input.dataset.removeContentImage = "";
        richEditorContainer.append(input);
      }
    });
  };

  const renderImageManager = () => {
    const images = imageOperations();
    const activeSlots = new Set(images.map((image) => image.slot));
    imageManager.replaceChildren();
    images.forEach(({ slot, index }) => {
      const row = document.createElement("div");
      row.className = "content-image-item";
      const label = document.createElement("span");
      label.textContent = `이미지 ${slot + 1}`;
      const cancelButton = document.createElement("button");
      cancelButton.type = "button";
      cancelButton.textContent = "선택 취소·삭제";
      cancelButton.addEventListener("click", () => {
        quill.deleteText(index, 1, "user");
        imageInputs[slot].value = "";
        selectedUploadFiles.delete(imageInputs[slot].name);
        const imageUrl = imageUrls.get(slot);
        if (imageUrl?.startsWith("blob:")) {
          URL.revokeObjectURL(imageUrl);
        }
        imageUrls.delete(slot);
      });
      row.append(label, cancelButton);
      imageManager.append(row);
    });
    addImageButton.disabled = images.length >= 5;
    addImageButton.textContent = `이미지 추가 (${images.length}/5)`;
    syncRemovalInputs(activeSlots);
  };

  const renderRichPreview = () => {
    const preview = richEditorContainer.querySelector("[data-rich-question-preview]");
    const value = quill.getText().trim();
    previewQueue = previewQueue.then(async () => {
      const mathJax = window.MathJax;
      if (mathJax?.startup?.document) {
        mathJax.startup.document.clearMathItemsWithin([preview]);
      }
      preview.textContent = value || "입력 내용이 여기에 표시됩니다.";
      if (value && mathJax?.typesetPromise) {
        await mathJax.typesetPromise([preview]);
      }
    }).catch(() => {
      preview.textContent = "수식 표기를 확인해 주세요.";
    });
  };

  const syncEditor = () => {
    textInput.value = quill.getText().trim();
    const documentData = quill.getContents();
    documentData.ops = documentData.ops.map((operation) => {
      const imageValue = operation.insert?.questionImage;
      if (imageValue === undefined) {
        return operation;
      }
      const slot = typeof imageValue === "object" ? imageValue.slot : imageValue;
      return {
        ...operation,
        insert: { questionImage: Number(slot) },
      };
    });
    documentInput.value = JSON.stringify(documentData);
    renderImageManager();
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(renderRichPreview, 250);
  };

  const storedDocument = richEditorContainer.dataset.document;
  if (storedDocument) {
    const documentData = JSON.parse(storedDocument);
    documentData.ops = documentData.ops.filter((operation) => {
      const imageValue = operation.insert?.questionImage;
      if (imageValue === undefined) {
        return true;
      }
      const slot = typeof imageValue === "object" ? imageValue.slot : imageValue;
      return imageUrls.has(Number(slot));
    }).map((operation) => {
      const imageValue = operation.insert?.questionImage;
      if (imageValue === undefined) {
        return operation;
      }
      const slot = Number(
        typeof imageValue === "object" ? imageValue.slot : imageValue
      );
      return {
        ...operation,
        insert: {
          questionImage: { slot, url: imageUrls.get(slot) || "" },
        },
      };
    });
    quill.setContents(documentData);
  } else {
    quill.setText(textInput.value);
    existingSlots.forEach((slot) => {
      quill.insertEmbed(
        Math.max(0, quill.getLength() - 1),
        "questionImage",
        { slot, url: imageUrls.get(slot) || "" },
        "silent"
      );
    });
  }

  quill.on("selection-change", (range) => {
    if (range) {
      selectedRange = range;
    }
  });
  quill.on("text-change", syncEditor);

  addImageButton.addEventListener("click", () => {
    const activeSlots = new Set(imageOperations().map((image) => image.slot));
    const freeSlot = imageInputs.findIndex((_, slot) => !activeSlots.has(slot));
    if (freeSlot >= 0) {
      imageInputs[freeSlot].click();
    }
  });

  imageInputs.forEach((input, slot) => {
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) {
        return;
      }
      const imageUrl = URL.createObjectURL(file);
      imageUrls.set(slot, imageUrl);
      const insertionIndex = selectedRange.index + selectedRange.length;
      quill.insertText(insertionIndex, "\n", "user");
      quill.insertEmbed(
        insertionIndex + 1,
        "questionImage",
        { slot, url: imageUrl },
        "user"
      );
      quill.insertText(insertionIndex + 2, "\n", "user");
      quill.setSelection(insertionIndex + 3, 0, "silent");
    });
  });

  const richFormulaMarker = "\uE000";
  const richFormulaTemplates = {
    inline: { template: `\\(${richFormulaMarker}\\)`, placeholder: "x" },
    fraction: {
      template: `\\(\\frac{${richFormulaMarker}}{b}\\)`,
      placeholder: "a",
    },
    power: { template: `\\(${richFormulaMarker}^{2}\\)`, placeholder: "x" },
    root: {
      template: `\\(\\sqrt{${richFormulaMarker}}\\)`,
      placeholder: "x",
    },
    sum: {
      template: `\\(\\sum_{i=1}^{n} ${richFormulaMarker}\\)`,
      placeholder: "x_i",
    },
  };
  richEditorContainer.querySelectorAll("[data-rich-math]").forEach((button) => {
    button.addEventListener("click", () => {
      const formulaTemplate = richFormulaTemplates[button.dataset.richMath];
      const selectedText = quill.getText(
        selectedRange.index,
        selectedRange.length
      );
      const replacement = selectedText || formulaTemplate.placeholder;
      const formula = formulaTemplate.template.replace(
        richFormulaMarker,
        replacement
      );
      const placeholderStart = formulaTemplate.template.indexOf(richFormulaMarker);
      quill.deleteText(selectedRange.index, selectedRange.length, "user");
      quill.insertText(selectedRange.index, formula, "user");
      if (selectedText) {
        quill.setSelection(selectedRange.index + formula.length, 0, "silent");
      } else {
        quill.setSelection(
          selectedRange.index + placeholderStart,
          replacement.length,
          "silent"
        );
      }
    });
  });

  questionForm.addEventListener("submit", syncEditor);
  window.addEventListener("load", renderRichPreview);
  syncEditor();
}

if (questionForm) {
  const mathEditors = questionForm.querySelectorAll("[data-math-editor]");
  const cursorMarker = "\uE000";
  const formulaTemplates = {
    inline: `\\(${cursorMarker}\\)`,
    display: `\\[\n${cursorMarker}\n\\]`,
    fraction: `\\(\\frac{${cursorMarker}}{b}\\)`,
    power: `\\(${cursorMarker}^{2}\\)`,
    root: `\\(\\sqrt{${cursorMarker}}\\)`,
    sum: `\\(\\sum_{i=1}^{n} ${cursorMarker}\\)`,
  };
  let previewQueue = Promise.resolve();

  const renderPreview = (editor) => {
    const input = editor.querySelector("[data-math-input]");
    const preview = editor.querySelector("[data-math-preview]");
    const value = input.value.trim();

    previewQueue = previewQueue.then(async () => {
      const mathJax = window.MathJax;
      if (mathJax?.startup?.document) {
        mathJax.startup.document.clearMathItemsWithin([preview]);
      }
      preview.textContent = value || "입력 내용이 여기에 표시됩니다.";
      preview.classList.toggle("empty", !value);
      preview.classList.remove("error");
      if (value && mathJax?.typesetPromise) {
        await mathJax.typesetPromise([preview]);
      }
    }).catch(() => {
      preview.classList.add("error");
      preview.textContent = "수식 표기를 확인해 주세요.";
    });
  };

  const insertFormula = (input, action) => {
    const template = formulaTemplates[action];
    if (!template) {
      return;
    }
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    const selectedText = input.value.slice(start, end);
    const insertedText = template.replace(cursorMarker, selectedText);
    const cursorPosition = selectedText
      ? start + insertedText.length
      : start + template.indexOf(cursorMarker);

    input.setRangeText(insertedText, start, end, "end");
    input.focus();
    input.setSelectionRange(cursorPosition, cursorPosition);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  mathEditors.forEach((editor) => {
    const input = editor.querySelector("[data-math-input]");
    let previewTimer;

    input.addEventListener("input", () => {
      window.clearTimeout(previewTimer);
      previewTimer = window.setTimeout(() => renderPreview(editor), 250);
    });
    editor.querySelectorAll("[data-math-action]").forEach((button) => {
      button.addEventListener("click", () => {
        insertFormula(input, button.dataset.mathAction);
      });
    });
  });

  window.addEventListener("load", () => {
    mathEditors.forEach(renderPreview);
  });
}

if (questionForm && window.Quill) {
  questionForm.querySelectorAll("[data-choice-rich-editor]").forEach(
    (container) => {
      const editorElement = container.querySelector("[data-choice-editor]");
      const textInput = container.querySelector("[data-choice-text]");
      const documentInput = container.querySelector("[data-choice-document]");
      const quill = new window.Quill(editorElement, {
        theme: "snow",
        placeholder: "선택지 내용을 입력하세요.",
        formats: ["bold", "italic", "underline"],
        modules: { toolbar: false },
      });

      try {
        const storedDocument = container.dataset.document;
        if (storedDocument) {
          quill.setContents(JSON.parse(storedDocument));
        } else {
          quill.setText(textInput.value);
        }
      } catch (error) {
        quill.setText(textInput.value);
      }

      const syncChoiceEditor = () => {
        textInput.value = quill.getText().trim();
        documentInput.value = JSON.stringify(quill.getContents());
      };
      quill.on("text-change", syncChoiceEditor);
      choiceRichEditors.set(Number(container.dataset.choiceIndex), quill);
      questionForm.addEventListener("submit", syncChoiceEditor);
      syncChoiceEditor();
    }
  );
}

const questionPreview = document.querySelector("[data-question-preview]");

if (questionForm && questionPreview) {
  const openPreviewButton = questionForm.querySelector(
    "[data-open-question-preview]"
  );
  const previewDocument = questionPreview.querySelector(
    "[data-preview-question-document]"
  );
  const previewChoices = questionPreview.querySelector("[data-preview-choices]");
  const previewShortAnswer = questionPreview.querySelector(
    "[data-preview-short-answer]"
  );
  const previewExplanation = questionPreview.querySelector(
    "[data-preview-explanation]"
  );
  let choicePreviewUrls = [];

  const clearChoicePreviewUrls = () => {
    choicePreviewUrls.forEach((url) => URL.revokeObjectURL(url));
    choicePreviewUrls = [];
  };

  const choiceImageUrl = (index) => {
    const fileInput = questionForm.querySelector(
      `input[name='choice_image_${index}']`
    );
    if (fileInput.files?.[0]) {
      const url = URL.createObjectURL(fileInput.files[0]);
      choicePreviewUrls.push(url);
      return url;
    }
    const removeInput = questionForm.querySelector(
      `input[name='remove_choice_image_${index}']`
    );
    if (removeInput?.checked) {
      return null;
    }
    return fileInput
      .closest(".choice-editor")
      .querySelector(".admin-choice-image-preview img")?.src || null;
  };

  const renderQuestionPreview = async () => {
    const mathJax = window.MathJax;
    if (mathJax?.startup?.document) {
      mathJax.startup.document.clearMathItemsWithin([questionPreview]);
    }
    clearChoicePreviewUrls();

    const richContent = questionForm.querySelector(
      "[data-rich-editor] .ql-editor"
    );
    previewDocument.replaceChildren();
    if (richContent) {
      const clonedContent = richContent.cloneNode(true);
      clonedContent.classList.add("ql-editor");
      previewDocument.append(clonedContent);
    } else {
      previewDocument.textContent = questionForm.elements.prompt.value;
    }

    const questionType = questionForm.elements.question_type.value;
    previewChoices.replaceChildren();
    previewChoices.hidden = questionType !== "multiple_choice";
    previewShortAnswer.hidden = questionType !== "short_answer";
    if (questionType === "multiple_choice") {
      const correctAnswers = new Set(
        Array.from(questionForm.querySelectorAll("input[name='answers']:checked"))
          .map((input) => input.value)
      );
      const answerType = correctAnswers.size > 1 ? "checkbox" : "radio";
      if (correctAnswers.size > 1) {
        const hint = document.createElement("p");
        hint.className = "answer-hint";
        hint.textContent = "복수 정답 문제입니다. 정답을 모두 선택하세요.";
        previewChoices.append(hint);
      }
      for (let index = 0; index < 4; index += 1) {
        const label = document.createElement("label");
        label.className = "choice-option";
        const line = document.createElement("div");
        line.className = "choice-line";
        const answerInput = document.createElement("input");
        answerInput.type = answerType;
        answerInput.disabled = true;
        const number = document.createElement("b");
        number.textContent = "①②③④"[index];
        const choiceContent = document.createElement("div");
        choiceContent.className = "choice-document";
        const choiceEditor = choiceRichEditors.get(index);
        const richChoiceContent = choiceEditor?.root.cloneNode(true);
        if (richChoiceContent && choiceEditor.getText().trim()) {
          choiceContent.append(richChoiceContent);
        } else {
          choiceContent.textContent = "선택지 내용";
        }
        line.append(answerInput, number, choiceContent);
        label.append(line);
        const imageUrl = choiceImageUrl(index);
        if (imageUrl) {
          const image = document.createElement("img");
          image.className = "choice-image";
          image.src = imageUrl;
          image.alt = `${index + 1}번 선택지 참고 이미지`;
          label.append(image);
        }
        previewChoices.append(label);
      }
    }

    previewExplanation.textContent =
      questionForm.elements.explanation.value || "해설 내용이 표시됩니다.";
    questionPreview.showModal();
    if (mathJax?.typesetPromise) {
      await mathJax.typesetPromise([questionPreview]);
    }
  };

  const closeQuestionPreview = () => {
    questionPreview.close();
    clearChoicePreviewUrls();
  };

  openPreviewButton.addEventListener("click", renderQuestionPreview);
  questionPreview.querySelectorAll("[data-close-question-preview]").forEach(
    (button) => button.addEventListener("click", closeQuestionPreview)
  );
  questionPreview.addEventListener("click", (event) => {
    if (event.target === questionPreview) {
      closeQuestionPreview();
    }
  });
  questionPreview.addEventListener("close", clearChoicePreviewUrls);
}
