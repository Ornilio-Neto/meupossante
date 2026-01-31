document.addEventListener("DOMContentLoaded", function () {
  const precoInput = document.getElementById("precoPorLitro");
  const litrosInput = document.getElementById("litros");
  const totalInput = document.getElementById("custoTotal");
  let lastEdited = null;

  function calculate() {
    const preco = parseFloat(precoInput.value) || 0;
    const litros = parseFloat(litrosInput.value) || 0;
    const total = parseFloat(totalInput.value) || 0;

    if (lastEdited === precoInput && litros > 0) {
      totalInput.value = (preco * litros).toFixed(2);
    } else if (lastEdited === litrosInput && preco > 0) {
      totalInput.value = (preco * litros).toFixed(2);
    } else if (lastEdited === totalInput && preco > 0) {
      litrosInput.value = (total / preco).toFixed(2);
    } else if (lastEdited === totalInput && litros > 0) {
      precoInput.value = (total / litros).toFixed(3);
    }
  }

  [precoInput, litrosInput, totalInput].forEach((input) => {
    input.addEventListener("focus", function () {
      lastEdited = this;
    });
    input.addEventListener("input", calculate);
  });

  const tipoCombustivelSelect = document.getElementById("tipoCombustivel");
  const newCombustivelWrapper = document.getElementById(
    "newCombustivelWrapper",
  );
  const newCombustivelInput = document.getElementById("newCombustivelName");

  tipoCombustivelSelect.addEventListener("change", function () {
    if (this.value === "add_new_combustivel") {
      newCombustivelWrapper.classList.remove("d-none");
      newCombustivelInput.required = true;
    } else {
      newCombustivelWrapper.classList.add("d-none");
      newCombustivelInput.required = false;
    }
  });
});
