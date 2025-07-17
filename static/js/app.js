console.log('App initialized');
document.addEventListener('DOMContentLoaded', () => {
  const progress = document.getElementById('progress');
  const progressValue = document.getElementById('progressValue');
  if (progress && progressValue) {
    progress.addEventListener('input', () => {
      progressValue.value = progress.value;
    });
  }
});
