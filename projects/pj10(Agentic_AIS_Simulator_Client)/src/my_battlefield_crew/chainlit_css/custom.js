// Step 텍스트 변경을 실시간 감지하여 애니메이션 클래스를 재적용하는 감시자
function initStepAnimationObserver() {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      // 텍스트 노드가 변경되었거나 자식 노드가 변경된 경우
      if (mutation.type === "characterData" || mutation.type === "childList") {
        const targetNode = mutation.target.nodeType === 3 ? mutation.target.parentElement : mutation.target;
        if (!targetNode) return;

        // Chainlit의 Step 관련 영역인지 탐색 (버튼, 스텝 타이틀 등)
        const stepContainer = targetNode.closest('button, [id*="step"], div[class*="step"]');
        if (stepContainer) {
          const textSpan = targetNode.tagName === "SPAN" ? targetNode : targetNode.querySelector("span");
          if (textSpan && !textSpan.classList.contains("animating")) {
            // Reflow 기법: 클래스를 제거 후 DOM 리플로우를 발생시켜 애니메이션 초기화
            textSpan.classList.remove("step-animate-trigger");
            void textSpan.offsetWidth; 
            textSpan.classList.add("step-animate-trigger");
          }
        }
      }
    });
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initStepAnimationObserver);
} else {
  initStepAnimationObserver();
}