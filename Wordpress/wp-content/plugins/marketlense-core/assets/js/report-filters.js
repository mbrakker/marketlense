(() => {
  "use strict";

  const formSelector = "[data-ml-live-filter-form]";
  const inputSelector = "[data-ml-live-filter-input]";
  const statusSelector = "[data-ml-filter-status]";
  const debounceDelay = 420;

  function prepareGetForm(form) {
    Array.from(form.elements).forEach((element) => {
      if (!(element instanceof HTMLInputElement || element instanceof HTMLSelectElement)) {
        return;
      }
      if (!element.name || element.value !== "") {
        return;
      }
      element.disabled = true;
    });
  }

  function submitForm(form) {
    const status = form.querySelector(statusSelector);
    if (status) {
      status.textContent = "Updating report filters.";
    }
    prepareGetForm(form);
    form.submit();
  }

  function initLiveFilterForm(form) {
    if (!(form instanceof HTMLFormElement) || form.dataset.mlLiveFilterReady === "true") {
      return;
    }

    let searchTimer = 0;
    let composing = false;

    form.addEventListener("submit", () => {
      prepareGetForm(form);
    });

    form.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLSelectElement) {
        window.clearTimeout(searchTimer);
        submitForm(form);
      }
    });

    form.querySelectorAll(inputSelector).forEach((input) => {
      if (!(input instanceof HTMLInputElement)) {
        return;
      }

      input.addEventListener("compositionstart", () => {
        composing = true;
      });
      input.addEventListener("compositionend", () => {
        composing = false;
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => submitForm(form), debounceDelay);
      });
      input.addEventListener("input", () => {
        if (composing) {
          return;
        }
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => submitForm(form), debounceDelay);
      });
    });

    form.dataset.mlLiveFilterReady = "true";
  }

  function init() {
    document.querySelectorAll(formSelector).forEach(initLiveFilterForm);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
