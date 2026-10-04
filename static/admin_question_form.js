const questionForm = document.querySelector(".admin-question-form");

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
