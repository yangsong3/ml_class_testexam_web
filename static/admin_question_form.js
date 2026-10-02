const questionForm = document.querySelector(".admin-question-form[data-id-recommendations]");

if (questionForm) {
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
