function openLightbox(src){

const lightbox = document.getElementById("lightbox");
const img = document.getElementById("lightbox-img");

lightbox.style.display = "block";
img.src = src;

}

function closeLightbox(){
document.getElementById("lightbox").style.display = "none";
}