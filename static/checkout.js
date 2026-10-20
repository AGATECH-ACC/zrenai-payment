let checkoutScript;
function loadCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (!checkoutScript) {
    checkoutScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => window.Razorpay ? resolve() : reject(new Error("Checkout unavailable."));
      script.onerror = () => {
        script.remove();
        checkoutScript = null;
        reject(new Error("Checkout could not load. Please check your connection."));
      };
      document.head.appendChild(script);
    });
  }
  return checkoutScript;
}
document.querySelectorAll(".buy-button").forEach(button => {
  button.addEventListener("click", async () => {
    const message = document.querySelector("#checkout-message");
    const original = button.innerHTML;
    button.disabled = true;
    button.textContent = "Preparing checkout…";
    message.hidden = true;
    try {
      await loadCheckout();
      const response = await fetch(button.dataset.endpoint || "/api/checkout/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value
        },
        body: JSON.stringify(button.dataset.product ? {product_id: Number(button.dataset.product)} : {})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not start checkout.");
      if (!data.checkout) {
        location.assign(data.purchase_url);
        return;
      }
      const checkout = new window.Razorpay({
        ...data.checkout,
        modal: {ondismiss() {
          message.textContent = "Checkout closed. You can resume this purchase or check its status in My purchases.";
          message.hidden = false;
        }}
      });
      checkout.open();
    } catch (error) {
      message.textContent = error.message || "Checkout unavailable. Please try again.";
      message.hidden = false;
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  });
});
