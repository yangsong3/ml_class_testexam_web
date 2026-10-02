const questionBuilder = document.querySelector("#question-builder");
const typeSelect = questionBuilder.elements.question_type;
const choiceFields = questionBuilder.querySelector("[data-choice-fields]");
const shortAnswerFields = questionBuilder.querySelector("[data-short-answer-fields]");
const choiceInputs = choiceFields.querySelectorAll("input[name='choice']");
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

questionBuilder.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const category = String(form.get("category"));
  const categorySelect = event.currentTarget.elements.category;
  const questionType = String(form.get("question_type"));
  const answers = questionType === "short_answer"
    ? String(form.get("text_answers")).split("\n").map((answer) => answer.trim()).filter(Boolean)
    : form.getAll("answers").map(Number);
  if (!answers.length) {
    window.alert("정답을 하나 이상 입력하거나 선택해 주세요.");
    return;
  }
  const question = {
    id: String(form.get("id")),
    category,
    category_name: categorySelect.options[categorySelect.selectedIndex].text,
    prompt: String(form.get("prompt")),
    type: questionType,
    choices: questionType === "short_answer" ? [] : form.getAll("choice").map(String),
    answers,
    explanation: String(form.get("explanation")),
  };
  const blob = new Blob([`${JSON.stringify(question, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${question.id}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});
