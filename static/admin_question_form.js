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
  const choiceInputs = choiceFields.querySelectorAll("input[name^='choice_']");
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
